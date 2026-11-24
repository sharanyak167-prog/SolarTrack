# SolarTrack

SolarTrack helps staff extract and review MESCOM HT bills, then calculate energy and savings from **verified** monthly readings. See [docs/FORMULAS.md](docs/FORMULAS.md) for the faculty's formulas. Period totals are sums of available verified months; the six-monthly/yearly rule is awaiting faculty confirmation. Rates are entered by staff, never inferred from bills.

## Important status and privacy notice

This is a **prototype, not cleared for production or public exposure**. Mock extraction works; live Gemini extraction and its schema, real-bill accuracy, MySQL 8, Windows/Python 3.14, and full browser/mobile behavior have not been verified in this delivery. The supplied repository did not contain the historical dataset claimed by its earlier UI. No historical records are bundled or invented. Reports use a default layout, not the faculty's sample. Protect any real bill and backup: they can contain personal/account data. Get college authorization and confirm Google Gemini's current data-handling terms before sending a bill to Gemini. Do not put API keys in files shared with others.

## Windows setup (PowerShell / VS Code)

1. Install Python 3.14 and the VS Code Python extension. Extract the ZIP and open the `solartrack` folder in VS Code. Open a PowerShell terminal in that folder.
2. Create and activate a virtual environment and install dependencies:

   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements.txt
   Copy-Item .env.example .env
   ```

   If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and retry, or use `cmd` and `.venv\Scripts\activate.bat` (`copy .env.example .env` in cmd). Do not commit or share `.env`.
3. Generate a random signing key with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Edit `.env` in VS Code: paste it as `JWT_SECRET_KEY=...`. The server will refuse to start without a key of at least 32 characters. Keep this value private and stable; changing it invalidates login tokens. `EXTRACTION_MODE=mock` is initially enabled: **every upload returns the same February 2025 sample regardless of the file**. It is only for testing, never real operation.
4. Create your first admin interactively:

   ```powershell
   cd backend
   python create_admin.py
   python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
   ```

   Choose and remember a strong password of at least 12 characters (at most 72 UTF-8 bytes). Open http://127.0.0.1:8000/ and log in. API documentation is at http://127.0.0.1:8000/docs. To stop, press Ctrl+C. Subsequent runs need only activation, `cd backend`, and the uvicorn command. Only the first admin is created by the script; add other admins/viewers in User Management.
5. For real extraction, set `EXTRACTION_MODE=gemini` and `GEMINI_API_KEY` in `.env` and restart. Run `python list_models.py` from `backend` with your own key to select currently accessible models; set `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`. Model names and quotas change; the defaults are examples, not a guarantee. Treat API failures or busy/quota errors as failures, not verified data. Never use a real key in a test or shared ZIP.

## Staff workflow

* Admin uploads a PDF, PNG or JPG (up to 15 MB); for a multi-page PDF select the relevant page if needed. Inspect the original beside extracted values. Check all three present/previous readings, three printed unit values, multipliers, month and dates against the paper bill. Correct errors, then explicitly verify. Errors block verification; warnings require human judgment. Only verified current bills appear in statistics and reports. Editing un-verifies a bill.
* Admin enters a savings rate for each month. No rate means savings are unknown. Dashboard and report warnings identify missing verified months and rates. Reports include monthly values and sums for a selected date range; sums are provisional until the faculty confirms the aggregation rule.
* Admin can download the CSV backfill template and import CSV or `.xlsx`. Supply actual present/previous readings, printed units, constants, dates and RR number for each row; missing readings are rejected, never fabricated. New rows require review and verification and do not overwrite existing bills. Historical CSV rows do not supply an original bill image; consult the physical source. Example values in the template are only the March 2025 answer-key example, not real historical records.
* The dashboard assumes one current connection in parts of its UI. Multiple-connection workflows require further work and testing. The original kVAh fields are stored as raw data, not used in the calculations.

## Testing

From the project root (with the venv activated): `python -m pytest -q`. Tests include mock upload → edit → verify → rate → dashboard API → PDF, formula answer keys, authorization, backfill, and SQLite backup. The current suite was run under Linux/Python 3.11, not Windows/Python 3.14. It does not demonstrate live Gemini or real extraction accuracy.

## Backup and restore (SQLite)

Admin can create/download a backup in System & Backups. It contains a SQLite online snapshot and files in the configured uploads directory; protect the ZIP and store a copy separately. For restore, stop the application, preserve the current database and uploads, then copy `database.sqlite` from the archive to the configured SQLite database path (default `dev.db` in project root) and restore the `uploads/` contents to the configured upload directory. Existing database records store upload paths; restore to the same path or migrate those paths. Restart and verify a few bills and reports. Backups do not include `.env`; keep configuration and keys separately in a secure location. Test restoration before relying on a backup.

MySQL automatic backup is deliberately disabled rather than producing an archive missing the database. Use `mysqldump` with a secure credential mechanism and back up uploads separately, then test restoration. ORM models are the current application schema; legacy SQL files are not guaranteed synchronized. `create_all` creates missing tables but does **not** migrate existing ones. MySQL 8 setup/migrations and end-to-end backup/restore need validation before use.

## Remaining manual work / known limitations

* Obtain the original `solartrack-v0.2.zip` if it contains files not present in this repository. Compare it with this folder.
* Run live Gemini against authorized real bills and compare every extracted field with paper; anonymize any golden fixtures, check scans and select/interpret pages. The referenced ten-page PDF was not supplied; the repository sample is one page and has no extractable text. Review that sample for sensitive information before distributing the project. Gemini's live structured schema and privacy/retention terms remain unverified.
* Obtain the faculty report sample and decisions on aggregation, kVAh, and number of connections. Add PDF charts and adjust the layout after approval. AI summaries have a numeric allowlist and fall back to deterministic text, but still need human review; they can be omitted.
* Validate schema and behavior on MySQL 8; introduce migrations and test them with realistic data. SQLite decimal storage has fixed database column scales and SQLite's numeric conversion limitations; arbitrary precision beyond those scales is not guaranteed. Review storage precision before using values requiring more than the schema supports.
* Perform a security review (including browser rendering of untrusted data, rate limiting, session storage, HTTPS/CSRF and deployment), accessibility, mobile and Windows/Python 3.14 testing. Do not expose this prototype on an untrusted network. Keep private files and backups access-controlled.
