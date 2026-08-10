#!/usr/bin/env python3
"""
Clean an existing data/data.json in place, applying the same identifier filter
that scripts/fetch_data.py now applies at fetch time.

data.json is committed to a public repository and served from a public GitHub
Pages URL, so a file written before that filter existed still exposes submitter
names and device IDs on every deploy until the next successful fetch. Run this
once after pulling the filter in, and any time a file is imported by hand.

    python scripts/scrub_data.py                # clean data/data.json
    python scripts/scrub_data.py path/to.json   # clean another file
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_data import (  # noqa: E402
    DROP_FIELDS,
    load_config,
    redact_record,
    strip_identifiers,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "data.json")
    if not os.path.exists(path):
        raise SystemExit(f"No such file: {path}")

    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    redact = bool(load_config().get("redact_narratives"))

    removed = set()
    for rec in doc.get("records", []):
        removed |= strip_identifiers(rec)
        redact_record(rec, redact)

    before = len(doc.get("fields", []))
    doc["fields"] = [f for f in doc.get("fields", []) if f.get("name") not in DROP_FIELDS]
    doc.setdefault("meta", {})["redacted"] = redact

    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Scrubbed {path}")
    print(f"  records            : {len(doc.get('records', []))}")
    print(f"  identifiers removed: {', '.join(sorted(removed)) or 'none'}")
    print(f"  schema fields      : {before} -> {len(doc['fields'])}")
    print(f"  narratives redacted: {redact}")


if __name__ == "__main__":
    main()
