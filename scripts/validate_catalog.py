#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SERIAL_RE = re.compile(r"^[A-Z]{4}-\d{5}$")
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


def valid_https(value: object) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme == "https" and bool(parsed.netloc)


def main() -> None:
    data = json.loads((ROOT / "textures.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    entries = data.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        entries = []
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append(f"{label}.id is required")
        elif entry_id in ids:
            errors.append(f"duplicate id: {entry_id}")
        ids.add(str(entry_id))
        serials = entry.get("serials", [])
        if not serials or any(not SERIAL_RE.fullmatch(str(value)) for value in serials):
            errors.append(f"{label}.serials must contain valid serials")
        for field in ("downloadUrl", "sourceUrl"):
            if not valid_https(entry.get(field)):
                errors.append(f"{label}.{field} must be an HTTPS URL")
        if not str(entry.get("downloadUrl", "")).lower().endswith(".zip"):
            errors.append(f"{label}.downloadUrl must point to a ZIP archive")
        if not HASH_RE.fullmatch(str(entry.get("sha256", ""))):
            errors.append(f"{label}.sha256 must be a SHA-256 digest")
        for field in ("sizeBytes", "fileCount"):
            if not isinstance(entry.get(field), int) or entry[field] < 1:
                errors.append(f"{label}.{field} must be positive")
        if not entry.get("authors"):
            errors.append(f"{label}.authors must not be empty")
        for preview in entry.get("previewUrls", []):
            if not valid_https(preview):
                errors.append(f"{label}.previewUrls contains an invalid URL")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Catalog valid: {len(entries)} entries")


if __name__ == "__main__":
    main()
