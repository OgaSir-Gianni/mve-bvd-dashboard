#!/usr/bin/env python3
"""
Fetch form definition + submissions from KoboToolbox and write a processed
`data/data.json` the static dashboard reads.

The API token is read from the KOBO_TOKEN environment variable and NEVER written
to disk, so it is safe to run in a public GitHub Actions workflow (token lives in
repo Secrets). Server + form UID come from config.json (overridable via env).

Run locally:
    export KOBO_TOKEN=xxxxxxxxxxxxxxxx
    python scripts/fetch_data.py
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# data/data.json is served from a public GitHub Pages URL, so anything left in a
# record is world-readable regardless of the dashboard's access gate. These
# fields identify the person or the handset behind a submission and carry no
# analytical value, so they are dropped before the file is written.
DROP_FIELDS = {
    "submitted_by", "username", "deviceid", "subscriberid", "simserial",
    "phonenumber", "imei", "uuid", "instanceid", "instanceID", "rootUuid",
    "meta", "audit", "audit_URL", "formhub", "__version__", "_uuid",
    "_submitted_by", "_validation_status", "_notes", "_tags", "_attachments",
    "start", "end", "today",
}

# Long free-text narratives can name localities, staff and security incidents.
# Set "redact_narratives": true in config.json to blank them in the public build
# while keeping every numeric indicator intact.
NARRATIVE_FIELDS = {
    "urgent_details", "daily_summary", "surveillance_update_note",
    "case_ipc_update_note", "lab_update_note", "sdb_update_note",
    "rcce_update_note", "ops_update_note", "hr_update_note",
    "funding_update_note", "prseah_update_note", "other_comments",
}


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    # env overrides (used by CI). Use "or" so an empty/undefined CI variable
    # falls back to config.json instead of becoming an empty string.
    cfg["server"] = (os.environ.get("KOBO_SERVER") or cfg["server"]).rstrip("/")
    cfg["asset_uid"] = os.environ.get("KOBO_ASSET_UID") or cfg["asset_uid"]
    return cfg


def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"HTTP {e.code} fetching {url}\n{body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error fetching {url}: {e}")


def build_schema(asset):
    """Return field metadata + choice-label lookup from the form definition."""
    content = asset.get("content", {})
    survey = content.get("survey", [])
    choice_lists = {}
    for c in content.get("choices", []):
        lst = c.get("list_name")
        name = c.get("name") or c.get("$autoname")
        label = c.get("label")
        if isinstance(label, list):
            label = label[0] if label else name
        choice_lists.setdefault(lst, {})[str(name)] = label or name

    fields = []
    geo_field = ""
    for q in survey:
        qtype = q.get("type", "")
        name = q.get("$autoname") or q.get("name")
        if not name or name in DROP_FIELDS:
            continue
        label = q.get("label")
        if isinstance(label, list):
            label = label[0] if label else name
        label = label or name

        entry = {"name": name, "label": label, "type": qtype}
        if qtype in ("select_one", "select_multiple"):
            list_name = q.get("select_from_list_name")
            entry["choices"] = choice_lists.get(list_name, {})
            entry["breakdown"] = True
        elif qtype in ("integer", "decimal", "range"):
            entry["numeric"] = True
        elif qtype in ("geopoint", "geoshape", "geotrace"):
            geo_field = geo_field or name
        fields.append(entry)

    return fields, geo_field


def fetch_all_submissions(server, uid, token):
    url = f"{server}/api/v2/assets/{uid}/data.json?limit=1000"
    results = []
    while url:
        page = api_get(url, token)
        results.extend(page.get("results", []))
        url = page.get("next")
    return results


def strip_identifiers(rec):
    """Drop identifying keys from an already-flattened record, in place.

    Returns the set of keys that were removed. Shared with scripts/scrub_data.py
    so a file committed before this filter existed can be cleaned the same way.
    """
    removed = {k for k in rec if k.split("/")[-1] in DROP_FIELDS}
    for k in removed:
        del rec[k]
    return {k.split("/")[-1] for k in removed}


def redact_record(rec, redact):
    """Blank narrative free-text fields when redaction is enabled, in place."""
    if not redact:
        return
    for f in NARRATIVE_FIELDS:
        if rec.get(f):
            rec[f] = "[texte libre retiré de la version publiée]"


def parse_geopoint(val):
    """Kobo geopoint = 'lat lon altitude accuracy' -> [lat, lon]."""
    if not val or not isinstance(val, str):
        return None
    parts = val.split()
    if len(parts) < 2:
        return None
    try:
        return [float(parts[0]), float(parts[1])]
    except ValueError:
        return None


def main():
    token = os.environ.get("KOBO_TOKEN")
    if not token:
        raise SystemExit("Set KOBO_TOKEN environment variable (your Kobo API token).")

    cfg = load_config()
    server, uid = cfg["server"], cfg["asset_uid"]
    if uid.startswith("REPLACE"):
        raise SystemExit("Set your form's asset UID in config.json (or KOBO_ASSET_UID).")

    print(f"Fetching form definition from {server} ...")
    asset = api_get(f"{server}/api/v2/assets/{uid}.json", token)
    fields, detected_geo = build_schema(asset)
    geo_field = cfg.get("geo_field") or detected_geo

    print("Fetching submissions ...")
    subs = fetch_all_submissions(server, uid, token)
    print(f"  {len(subs)} submissions")

    # Slim records: keep non-internal fields + parse geo
    redact = bool(cfg.get("redact_narratives"))
    records = []
    dropped = set()
    for s in subs:
        rec = {}
        for k, v in s.items():
            leaf = k.split("/")[-1] if "/" in k else k
            if leaf in DROP_FIELDS:
                dropped.add(leaf)
                continue
            if k in ("_submission_time", "_id"):
                rec[k] = v
            elif not k.startswith("_") and "/" not in k:
                rec[k] = v
            elif "/" in k:  # grouped field: keep leaf name
                rec[leaf] = v
        redact_record(rec, redact)
        if geo_field:
            pt = parse_geopoint(s.get(geo_field) or rec.get(geo_field.split("/")[-1]))
            if pt:
                rec["_geo"] = pt
        records.append(rec)

    if dropped:
        print(f"  removed identifying fields: {', '.join(sorted(dropped))}")
    if redact:
        print("  narrative free-text fields redacted (redact_narratives=true)")

    out = {
        "meta": {
            # config.json wins so the displayed title can be changed without
            # renaming the Kobo form itself.
            "title": cfg.get("title") or asset.get("name") or "Kobo Dashboard",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(records),
            "geo_field": geo_field,
            "redacted": redact,
        },
        "fields": fields,
        "records": records[: cfg.get("max_table_rows", 5000) + 100000],
    }

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    out_path = os.path.join(ROOT, "data", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main()
