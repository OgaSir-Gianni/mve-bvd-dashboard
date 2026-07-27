# Kobo Dashboard

A live, public dashboard for a KoboToolbox form. A scheduled GitHub Action pulls
submissions from the Kobo API, saves them as JSON, and publishes a static site to
GitHub Pages. Your API token stays a secret — it is never in the code or the page.

An operations-focused view of the MVE/BVD daily field sitrep (WHO-branded):

- **Vue d'ensemble des opérations** — plain-language headline for leadership
- **Operational KPIs** — zones reporting, % alerts investigated, % contacts seen, community relays, red zones, bottlenecks
- **Field status today** (🟢/🟠/🔴), operational bottlenecks, urgent issues
- **FieldCo reporting** — how many reports each field coordinator submitted
- **Where the action is** — response-pillar activity (surveillance, IPC/WASH, lab, burials, RCCE, ops, HR, funding, PRSEAH)
- **Priorities** for the next 24–48h (colour-matched to the pillars)
- **% alerts investigated per zone** and **% contacts followed per zone**
- **Daily narrative feed** — summaries and urgent flags, filterable by 🔴/🟠/🟢
- **Completeness heatmap** — reporting completeness of operational indicators, per province over time
- **Province & reporting-date filters**, filterable/sortable table
- **PDF briefing**, **light/dark mode**, **password gate**, and a **manual import failsafe**

## Failsafe: manual data import

If the automatic Kobo link ever breaks, you can keep the dashboard up to date by hand:

1. In Kobo, open the project → **Data → Downloads → XLS** (or CSV), download the export.
2. On the dashboard, click **⬆ Importer (secours)** and choose that file.

The dashboard parses the export in your browser, updates every chart, KPI and the PDF,
and shows an amber banner noting you're on manually-imported data. The import is remembered
across reloads until you click **Revenir aux données automatiques**. No re-deploy needed.

## Architecture

```
Kobo API ──(hourly, token in Secrets)──▶ scripts/fetch_data.py ──▶ data/data.json ──▶ index.html ──▶ GitHub Pages
```

The token lives in GitHub **Secrets**, only the CI runner sees it, and the browser
only ever loads the already-fetched `data.json`. Safe to make the repo public.

## One-time setup

### 1. Get your Kobo details
- **Server**: `https://eu.kobotoolbox.org` (EU) or `https://kf.kobotoolbox.org` (global). Use whichever you log in to.
- **Form UID**: open your project in Kobo → the URL contains `/forms/aXXXXXXXXXXXX` — that `aXXX…` string is the UID.
- **API token**: Kobo → **Account Settings → Security → API key** (or visit `<server>/token/?format=json`).

### 2. Fill in `config.json`
Set `server` and `asset_uid`. (`geo_field` is auto-detected; only set it if the map is empty and you know the field name.)

### 3. Push to GitHub
```bash
git init && git add . && git commit -m "Kobo dashboard"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 4. Add the secret + variables (repo → Settings)
- **Secrets and variables → Actions → Secrets**: add `KOBO_TOKEN` = your API token.
- **Variables** (optional, overrides `config.json`): `KOBO_SERVER`, `KOBO_ASSET_UID`.

### 5. Enable Pages
Repo → **Settings → Pages → Source: GitHub Actions**.

### 6. Run it
Repo → **Actions → "Update Kobo data & deploy" → Run workflow**. When it finishes,
your site is live at `https://<you>.github.io/<repo>/`. It then refreshes **every hour**.

## Run locally

```bash
export KOBO_TOKEN=your_token_here      # Windows: set KOBO_TOKEN=...
python scripts/fetch_data.py           # writes data/data.json
python -m http.server 8000             # open http://localhost:8000
```

## Files
| File | Purpose |
|------|---------|
| `config.json` | Server, form UID, options |
| `scripts/fetch_data.py` | Fetches + processes Kobo data (token from env) |
| `index.html` | The dashboard (Chart.js + Leaflet, no build step) |
| `.github/workflows/update-and-deploy.yml` | Hourly fetch + Pages deploy |
| `data/data.json` | Generated data (regenerated each run) |

## Tuning
- **Refresh rate**: edit the `cron` in the workflow (`0 * * * *` = hourly; `*/15 * * * *` = every 15 min).
- **Table columns**: `tableColumns()` in `index.html` shows the first 12 fields — adjust the slice.
