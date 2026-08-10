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
- **PDF briefing**, **light/dark mode**, **access gate**, and a **manual import failsafe**

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
only ever loads the already-fetched `data.json`.

## What is public, and what the access gate does not do

The repo is public and the site is a static GitHub Pages deployment, so
**`data/data.json` is fetchable by anyone who knows the URL** — the login form
runs in the browser *after* that file is already downloadable. Treat the gate as
deterrence against casual browsing, nothing more.

Because of that, the published dataset is filtered rather than protected:

- `scripts/fetch_data.py` drops every identifying field (`submitted_by`,
  `deviceid`, `username`, submission UUIDs, device timestamps) before writing
  `data/data.json`. `DROP_FIELDS` in that file is the list.
- `scripts/scrub_data.py` applies the same filter to a file that already exists,
  for anything committed before the filter was added.
- `scripts/verify_public_build.py` runs in CI **before** the Pages upload and
  fails the deploy if an identifier survives.
- `index.html` sends `noindex, nofollow, noarchive` so the page and its data are
  not meant to be indexed.

Free-text narratives (`urgent_details`, the per-pillar notes) are **still
published**, because they are what the briefing feed is for. Some of them
describe security incidents and name localities. If that is not acceptable for
your context, set `"redact_narratives": true` in `config.json` — every numeric
indicator keeps working and the free text is replaced with a placeholder.

If the data genuinely must stay confidential, a static host cannot deliver that.
Move to something that authenticates the request itself: a private repo behind
Cloudflare Access, Netlify password protection, or an authenticating proxy.

### Changing the access credentials

The gate stores a PBKDF2-HMAC-SHA256 hash (250,000 iterations, random salt) of
`username:password` in the `GATE` constant in `index.html`. Never put the
password itself in a commit message, a filename, or an issue. To rotate it:

```bash
python3 - <<'EOF'
import hashlib, secrets, binascii
user, pw = "oms", "your-new-password"
salt = secrets.token_bytes(16); iters = 250000
dk = hashlib.pbkdf2_hmac("sha256", f"{user}:{pw}".encode(), salt, iters, 32)
print("salt:", binascii.hexlify(salt).decode())
print("hash:", binascii.hexlify(dk).decode())
EOF
```

Paste the two values into `GATE` in `index.html` and share the password out of
band. Anyone who had the old one keeps nothing, but note the old hash stays in
git history — so never reuse a password across systems.

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
| `config.json` | Server, form UID, title, narrative redaction switch |
| `scripts/fetch_data.py` | Fetches + processes Kobo data, drops identifying fields |
| `scripts/scrub_data.py` | Applies the same filter to an existing `data.json` |
| `scripts/verify_public_build.py` | CI gate: fails the deploy if personal data would ship |
| `index.html` | The dashboard (Chart.js + Leaflet, no build step) |
| `assets/vendor/xlsx.full.min.js` | SheetJS 0.20.3, vendored — parses manual imports |
| `.github/workflows/update-and-deploy.yml` | Hourly fetch, scrub, verify, Pages deploy |
| `data/data.json` | Generated data (regenerated each run) |
| `robots.txt`, `404.html` | Crawler policy and a branded not-found page |

## Tuning
- **Refresh rate**: edit the `cron` in the workflow (`0 * * * *` = hourly; `*/15 * * * *` = every 15 min).
- **Table columns**: `TBL_COLS` in `index.html`.
- **Title**: `title` in `config.json` and the `<h1 id="title">` in `index.html`.
- **Entry-page note**: the `.gate-note` block in `index.html`.

## Resilience notes
- The hourly fetch is allowed to fail without blocking a deploy, so the site
  stays up on the last good data. When that happens the run is annotated with a
  warning and the dashboard shows a banner giving the age of the data.
- Chart.js and Leaflet come from CDNs. If either is unreachable the dashboard
  still renders KPIs, the feed, the table and the heatmap, and shows a per-chart
  fallback message instead of a blank page.
- jsPDF and SheetJS load only when the export or import button is first clicked,
  keeping ~1.2 MB out of the initial page load.
