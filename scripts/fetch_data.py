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


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    # env overrides (used by CI)
    cfg["server"] = os.environ.get("KOBO_SERVER", cfg["server"]).rstrip("/")
    cfg["asset_uid"] = os.environ.get("KOBO_ASSET_UID", cfg["asset_uid"])
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
        if not name:
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
    records = []
    for s in subs:
        rec = {}
        for k, v in s.items():
            if k in ("_submission_time", "_id"):
                rec[k] = v
            elif not k.startswith("_") and "/" not in k:
                rec[k] = v
            elif "/" in k:  # grouped field: keep leaf name
                rec[k.split("/")[-1]] = v
        if geo_field:
            pt = parse_geopoint(s.get(geo_field) or rec.get(geo_field.split("/")[-1]))
            if pt:
                rec["_geo"] = pt
        records.append(rec)

    out = {
        "meta": {
            "title": asset.get("name") or cfg.get("title", "Kobo Dashboard"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(records),
            "geo_field": geo_field,
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
