# SolarTrack — MESCOM HT Bill Energy Analytics
SolarTrack reads MESCOM HT electricity bills (PDF or image) with Google Gemini, validates extracted readings, lets staff review and verify, then calculates solar generation, grid import/export, net energy, and savings using exact `Decimal` arithmetic. Verified data powers an interactive dashboard and downloadable PDF reports.
**Stack:** Python 3.14, FastAPI, SQLAlchemy, SQLite (dev) / MySQL 8 (prod), Google Gemini API (`google-genai`), HTML/CSS/JS + Chart.js, ReportLab.
---
## Windows Quick Start (PowerShell / VS Code)
### Prerequisites
- **Python 3.14** — confirm with `python --version`
- **Google Gemini API key** — get one at [aistudio.google.com](https://aistudio.google.com) *(optional if using `EXTRACTION_MODE=mock`)*
- **MySQL 8.0+** *(optional for dev; required for MySQL production)*
### 1. Create virtual environment & install dependencies
Open PowerShell in the `solartrack\` folder:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```
> If PowerShell blocks activation, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
### 2. Configure `.env`
```powershell
Copy-Item .env.example .env
notepad .env
```
Generate a random `JWT_SECRET_KEY`:
```powershell
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
```