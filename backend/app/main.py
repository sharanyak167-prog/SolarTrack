"""FastAPI application for SolarTrack.

Manages MESCOM HT electricity bill ingestion, Gemini extraction, staff verification,
energy analytics, user authentication & RBAC, PDF report generation, and data backfill.
"""
from dataclasses import asdict
from datetime import date
import io
from pathlib import Path
from typing import Optional

from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     Request, UploadFile, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import auth, backup, config, db, services
from .auth import (LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate,
                   get_current_user, hash_password, require_admin,
                   require_viewer_or_admin, verify_password)
from .backfill import import_records, parse_csv_content, parse_excel_content
from .models import AuditLog, Bill, BillFile, Connection, MonthlyRate, User
from .reports.ai_summary import generate_executive_summary
from .reports.generator import INCEPTION_DATE, generate_report_pdf
from .schemas import (BillEdit, BillOut, ConnectionOut, EnergyOut, MonthRow,
                      RateIn, RateOut, SummaryOut)


def bill_out(s: Session, bill: Bill) -> BillOut:
    out = BillOut.model_validate(bill)
    out.rate_per_unit = services.rate_for(s, bill.connection_id, bill.bill_month)
    out.energy = EnergyOut(**asdict(services.energy_for(bill, out.rate_per_unit)))
    return out


def create_app(database_url: Optional[str] = None) -> FastAPI:
    auth.jwt_secret()  # Fail closed before serving requests.
    db.init_db(database_url or config.database_url())
    app = FastAPI(title="SolarTrack", version="0.2.0")

    Session_ = Depends(db.get_session)
    Admin_ = Depends(require_admin)
    User_ = Depends(require_viewer_or_admin)

    # Health & System Status
    @app.get("/health")
    def health():
        return {
            "ok": True,
            "system": "SolarTrack",
            "version": "0.2.0",
            "extraction_mode": config.extraction_mode(),
            "primary_model": config.gemini_model(),
            "fallback_models": config.gemini_models(),
        }

    # ================= AUTHENTICATION & USERS =================

    @app.post("/auth/login", response_model=TokenResponse)
    def login(req: LoginRequest, s: Session = Session_):
        user = s.scalar(select(User).where(User.username == req.username))
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated",
            )
        token = auth.create_access_token({"sub": user.username, "role": user.role})
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            role=user.role,
            username=user.username,
            full_name=user.full_name,
        )

    @app.get("/auth/me", response_model=UserOut)
    def get_me(current_user: User = Depends(get_current_user)):
        return current_user

    @app.get("/users", response_model=list[UserOut])
    def list_users(current_user: User = Admin_, s: Session = Session_):
        return list(s.scalars(select(User).order_by(User.id)))

    @app.post("/users", response_model=UserOut, status_code=201)
    def create_user(body: UserCreate, current_user: User = Admin_, s: Session = Session_):
        existing = s.scalar(select(User).where(User.username == body.username))
        if existing:
            raise HTTPException(409, f"Username '{body.username}' already exists")
        if body.role not in ("admin", "viewer"):
            raise HTTPException(422, "Role must be 'admin' or 'viewer'")
        new_u = User(
            username=body.username,
            hashed_password=hash_password(body.password),
            full_name=body.full_name,
            role=body.role,
            is_active=True,
        )
        s.add(new_u)
        s.commit()
        return new_u

    @app.patch("/users/{user_id}", response_model=UserOut)
    def update_user(user_id: int, body: UserUpdate, current_user: User = Admin_, s: Session = Session_):
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "User not found")
        if u.id == current_user.id and body.role is not None and body.role != "admin":
            raise HTTPException(400, "You cannot remove your own admin role")
        if body.full_name is not None:
            u.full_name = body.full_name
        if body.role is not None:
            if body.role not in ("admin", "viewer"):
                raise HTTPException(422, "Role must be 'admin' or 'viewer'")
            u.role = body.role
        if body.password is not None and body.password.strip():
            u.hashed_password = hash_password(body.password)
        if body.is_active is not None:
            if u.id == current_user.id and body.is_active is False:
                raise HTTPException(400, "You cannot deactivate your own account")
            u.is_active = body.is_active
        s.commit()
        return u

    @app.delete("/users/{user_id}", status_code=204)
    def delete_user(user_id: int, current_user: User = Admin_, s: Session = Session_):
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "User not found")
        if u.id == current_user.id:
            raise HTTPException(400, "You cannot delete your own account")
        s.delete(u)
        s.commit()
        return Response(status_code=204)

    # ================= BILLS & EXTRACTION =================

    @app.post("/bills/upload", response_model=BillOut, status_code=201)
    async def upload(
        file: UploadFile = File(...),
        replace: bool = False,
        page: Optional[int] = Query(None, description="1-based page number for multi-page PDFs"),
        current_user: User = Admin_,
        s: Session = Session_,
    ):
        data = await file.read(config.MAX_UPLOAD_BYTES + 1)
        bill = services.ingest_upload(
            s,
            filename=file.filename or "upload",
            data=data,
            user=current_user.username,
            replace=replace,
            page_num=page,
        )
        return bill_out(s, bill)

    @app.post("/bills/inspect-pages")
    async def inspect_pages(file: UploadFile = File(...), current_user: User = Admin_):
        data = await file.read(config.MAX_UPLOAD_BYTES + 1)
        ext = Path(file.filename or "").suffix.lower()
        if ext != ".pdf":
            return {"filename": file.filename, "page_count": 1, "is_pdf": False}
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(data))
            return {
                "filename": file.filename,
                "page_count": len(reader.pages),
                "is_pdf": True,
            }
        except Exception as e:
            return {"filename": file.filename, "page_count": 1, "error": str(e)}

    @app.get("/bills", response_model=list[BillOut])
    def list_bills(
        status: Optional[str] = None,
        connection_id: Optional[int] = None,
        year: Optional[int] = None,
        include_old_versions: bool = False,
        current_user: User = User_,
        s: Session = Session_,
    ):
        q = select(Bill).order_by(Bill.bill_month.desc(), Bill.version.desc())
        if status:
            q = q.where(Bill.status == status)
        if connection_id:
            q = q.where(Bill.connection_id == connection_id)
        if not include_old_versions:
            q = q.where(Bill.is_current.is_(True))
        bills = list(s.scalars(q))
        if year:
            bills = [b for b in bills if b.bill_month.year == year]
        return [bill_out(s, b) for b in bills]

    @app.get("/bills/{bill_id}", response_model=BillOut)
    def get_bill(bill_id: int, current_user: User = User_, s: Session = Session_):
        return bill_out(s, services.get_bill_or_404(s, bill_id))

    @app.get("/bills/{bill_id}/file")
    def get_bill_file(bill_id: int, current_user: User = User_, s: Session = Session_):
        bill = services.get_bill_or_404(s, bill_id)
        f = s.get(BillFile, bill.file_id)
        if not f or not Path(f.stored_path).is_file():
            raise HTTPException(404, "Original file is missing")
        return FileResponse(f.stored_path, media_type=f.mime_type, filename=f.original_name)

    @app.patch("/bills/{bill_id}", response_model=BillOut)
    def edit(
        bill_id: int,
        body: BillEdit,
        current_user: User = Admin_,
        s: Session = Session_,
    ):
        bill = services.get_bill_or_404(s, bill_id)
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        return bill_out(s, services.edit_bill(s, bill, changes, current_user.username))

    @app.post("/bills/{bill_id}/verify", response_model=BillOut)
    def verify(bill_id: int, current_user: User = Admin_, s: Session = Session_):
        return bill_out(s, services.verify_bill(s, services.get_bill_or_404(s, bill_id), current_user.username))

    @app.post("/bills/{bill_id}/reject", response_model=BillOut)
    def reject(bill_id: int, current_user: User = Admin_, s: Session = Session_):
        return bill_out(s, services.reject_bill(s, services.get_bill_or_404(s, bill_id), current_user.username))

    @app.delete("/bills/{bill_id}", status_code=204)
    def delete_bill(bill_id: int, current_user: User = Admin_, s: Session = Session_):
        bill = services.get_bill_or_404(s, bill_id)
        services.delete_bill(s, bill, current_user.username)
        return Response(status_code=204)

    # ================= CONNECTIONS & RATES =================

    @app.get("/connections", response_model=list[ConnectionOut])
    def connections(current_user: User = User_, s: Session = Session_):
        return list(s.scalars(select(Connection).order_by(Connection.id)))

    @app.put("/rates", response_model=RateOut)
    def put_rate(body: RateIn, current_user: User = Admin_, s: Session = Session_):
        return services.set_rate(s, body.connection_id, body.bill_month, body.rate_per_unit, current_user.username)

    @app.get("/rates", response_model=list[RateOut])
    def list_rates(connection_id: int, current_user: User = User_, s: Session = Session_):
        return list(s.scalars(
            select(MonthlyRate).where(MonthlyRate.connection_id == connection_id).order_by(MonthlyRate.bill_month)
        ))

    # ================= STATS & ANALYTICS =================

    @app.get("/stats/monthly", response_model=list[MonthRow])
    def stats_monthly(
        connection_id: int,
        start: Optional[date] = None,
        end: Optional[date] = None,
        current_user: User = User_,
        s: Session = Session_,
    ):
        rows = []
        for b in services.verified_bills(s, connection_id, start, end):
            rate = services.rate_for(s, connection_id, b.bill_month)
            rows.append(MonthRow(
                bill_id=b.id,
                bill_month=b.bill_month,
                rate_per_unit=rate,
                energy=EnergyOut(**asdict(services.energy_for(b, rate))),
            ))
        return rows

    @app.get("/stats/summary", response_model=SummaryOut)
    def stats_summary(
        connection_id: int,
        start: date = Query(...),
        end: date = Query(...),
        current_user: User = User_,
        s: Session = Session_,
    ):
        return services.summary(s, connection_id, start, end)

    # ================= PDF REPORTS & AI SUMMARIES =================

    @app.get("/reports/download")
    def download_report_pdf(
        connection_id: int,
        start: date = Query(...),
        end: date = Query(...),
        include_ai: bool = Query(True),
        current_user: User = User_,
        s: Session = Session_,
    ):
        conn = s.get(Connection, connection_id)
        if not conn:
            raise HTTPException(404, "Connection not found")

        bills = services.verified_bills(s, connection_id, start, end)
        if not bills:
            raise HTTPException(404, "No verified bills found for the requested period")

        months_list = []
        for b in bills:
            r = services.rate_for(s, connection_id, b.bill_month)
            e = services.energy_for(b, r)
            cum = services.get_cumulative_stats(s, connection_id, b.bill_month)
            months_list.append({
                "bill_month": b.bill_month.isoformat(),
                "month_label": b.bill_month_label or b.bill_month.strftime("%b-%y"),
                "rate_per_unit": r,
                "energy": asdict(e),
                "cumulative_units": cum["total_units"],
                "cumulative_savings": cum["total_savings"],
            })

        summ = services.summary(s, connection_id, start, end)
        overall_cum = services.get_cumulative_stats(s, connection_id, end)

        pdf_bytes = generate_report_pdf(
            connection_details={"rr_number": conn.rr_number, "consumer_name": conn.consumer_name},
            start_date=start,
            end_date=end,
            months_data=months_list,
            summary_data=summ,
            cumulative_data=overall_cum,
            include_ai_summary=include_ai,
        )

        filename = f"SolarTrack_Report_{start.strftime('%Y%m')}_{end.strftime('%Y%m')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.post("/reports/ai-summary")
    def ai_summary_endpoint(body: dict, current_user: User = User_):
        return generate_executive_summary(body)

    # ================= HISTORICAL BACKFILL =================

    @app.post("/backfill/import")
    async def backfill_import(file: UploadFile = File(...), current_user: User = Admin_, s: Session = Session_):
        content = await file.read(config.MAX_UPLOAD_BYTES + 1)
        if len(content) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File exceeds upload size limit")
        filename = (file.filename or "").lower()
        if filename.endswith(".csv"):
            records = parse_csv_content(content.decode("utf-8", errors="replace"))
        elif filename.endswith(".xlsx"):
            records = parse_excel_content(content)
        else:
            raise HTTPException(415, "Please upload a CSV or Excel (.xlsx) file")

        if not records:
            raise HTTPException(400, "The uploaded file contains no data rows")

        res = import_records(s, records, user=current_user.username)
        return res

    @app.get("/backfill/template")
    def backfill_template():
        template_csv = (
            "bill_month,period_start,period_end,rr_number,solar_prev,solar_present,solar_units_printed,"
            "import_prev,import_present,import_units_printed,export_prev,export_present,export_units_printed,"
            "solar_constant,meter_constant,net_import_printed,rate_per_unit\n"
            "2025-03-01,2025-03-01,2025-04-01,EXAMPLE,14107.17,14478.19,37102,"
            "1524.2360,1562.8340,77196,75.1480,76.4530,2610,100,2000,74586,7\n"
        )
        return Response(
            content=template_csv,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=solar_backfill_template.csv"},
        )

    # ================= BACKUP & AUDIT LOG =================

    @app.post("/backup/create")
    def create_backup_endpoint(current_user: User = Admin_):
        path = backup.create_backup()
        return {"success": True, "backup_file": path.name, "path": str(path)}

    @app.get("/backup/list")
    def list_backups_endpoint(current_user: User = Admin_):
        return backup.list_backups()

    @app.get("/backup/download")
    def download_latest_backup(filename: Optional[str] = None, current_user: User = Admin_):
        backups = backup.list_backups()
        if not backups:
            raise HTTPException(404, "No backups available")
        target = backups[0]["path"]
        if filename:
            match = [b for b in backups if b["filename"] == filename]
            if match:
                target = match[0]["path"]
        return FileResponse(target, media_type="application/zip", filename=Path(target).name)

    @app.get("/audit-log")
    def get_audit_log(
        limit: int = 100,
        bill_id: Optional[int] = None,
        current_user: User = Admin_,
        s: Session = Session_,
    ):
        q = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        if bill_id:
            q = q.where(AuditLog.bill_id == bill_id)
        return list(s.scalars(q))

    # ================= FRONTEND WEB UI =================

    frontend_dir = config.ROOT / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/", response_class=FileResponse)
        def index_page():
            return FileResponse(frontend_dir / "index.html")

    return app
