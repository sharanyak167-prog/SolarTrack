# SolarTrack

Reads MESCOM bills with Gemini, validates them, lets staff verify, then calculates
solar / import / export / consumption / savings (rules: `docs/FORMULAS.md`).

## Run (from this folder)

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell  (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env ; then edit .env
cd backend
python -m uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000/docs to try every endpoint. Run tests with `python3 -m pytest` from this folder.

## Flow

1. `POST /bills/upload` (PDF/PNG/JPG). Gemini extracts, validation runs, status becomes `extracted` or `needs_review`.
2. `GET /bills/{id}` and `/bills/{id}/file`: the reviewer compares values with the original.
3. `PATCH /bills/{id}` to correct values (audited, re-validated, un-verifies the bill).
4. `POST /bills/{id}/verify`: blocked while any `error` flag remains.
5. `PUT /rates`: staff enter that month's savings rate (Rs/unit). No default.
6. `GET /stats/monthly` and `GET /stats/summary`: verified bills only.

Decimals are returned as exact strings (e.g. `"37102.00"`); convert with `Number()` only for charts.

## Not built yet

- Login / roles (X-User header only labels the audit log).
- Frontend (review screen, dashboard), PDF reports, AI summaries, historical import.
- Gemini extraction has NOT been run against a real bill (no API key was available while building);
  everything else is tested with mock extraction.
