#!/usr/bin/env python3
"""
Fail the build if anything about to be published would expose personal data.

data/data.json is served from a public URL with no authentication in front of
it, so this runs in CI between the fetch and the Pages upload. It is the last
thing standing between a mistake in the fetch filter and 121 named field staff
on the open internet.

    python scripts/verify_public_build.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_data import DROP_FIELDS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Values that should never appear in a published record, regardless of key.
VALUE_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "email address"),
    (re.compile(r"ee\.kobotoolbox\.org:[A-Za-z0-9]+"), "Kobo device id"),
    (re.compile(r"\bToken\s+[a-f0-9]{40}\b"), "Kobo API token"),
]


def main():
    path = os.path.join(ROOT, "data", "data.json")
    if not os.path.exists(path):
        print(f"note: {path} absent — nothing to verify")
        return 0

    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    problems = []

    for i, rec in enumerate(doc.get("records", [])):
        for key in rec:
            if key.split("/")[-1] in DROP_FIELDS:
                problems.append(f"record {i}: identifying field {key!r} present")
        for key, val in rec.items():
            if not isinstance(val, str):
                continue
            for pattern, what in VALUE_PATTERNS:
                if pattern.search(val):
                    problems.append(f"record {i}: {what} in field {key!r}")

    for field in doc.get("fields", []):
        if field.get("name") in DROP_FIELDS:
            problems.append(f"schema exposes identifying field {field['name']!r}")

    if problems:
        print("PUBLIC BUILD BLOCKED — personal data found in data/data.json:\n")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        print("\nRun `python scripts/scrub_data.py` and commit the result.")
        return 1

    print(f"OK — {len(doc.get('records', []))} records carry no identifying fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
