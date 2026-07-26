#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SERIAL_RE = re.compile(r"^[A-Z]{4}-\d{5}$")
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_TEXTURE_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_TEXTURE_FILE_COUNT = 50_000


def valid_https(value: object) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme == "https" and bool(parsed.netloc)


def main() -> None:
    catalog_path = ROOT / "textures.json"
    if catalog_path.stat().st_size > MAX_CATALOG_BYTES:
        raise SystemExit("textures.json exceeds the application's 8 MiB catalog limit")
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    entries = data.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        entries = []
    ids: set[str] = set()
    download_urls: dict[str, str] = {}
    archive_hashes: dict[str, str] = {}
    catalog_by_id: dict[str, dict[str, object]] = {}
    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append(f"{label}.id is required")
        elif entry_id in ids:
            errors.append(f"duplicate id: {entry_id}")
        ids.add(str(entry_id))
        if isinstance(entry_id, str):
            catalog_by_id[entry_id] = entry
        serials = entry.get("serials", [])
        if not serials or any(not SERIAL_RE.fullmatch(str(value)) for value in serials):
            errors.append(f"{label}.serials must contain valid serials")
        elif len(serials) != len(set(serials)):
            errors.append(f"{label}.serials contains duplicates")
        for field in ("downloadUrl", "sourceUrl"):
            if not valid_https(entry.get(field)):
                errors.append(f"{label}.{field} must be an HTTPS URL")
        download_url = str(entry.get("downloadUrl", ""))
        if not download_url.lower().endswith(".zip"):
            errors.append(f"{label}.downloadUrl must point to a ZIP archive")
        download_key = download_url.casefold()
        if download_key in download_urls:
            errors.append(
                f"duplicate downloadUrl: {download_url} "
                f"({download_urls[download_key]} and {entry_id})"
            )
        elif download_url:
            download_urls[download_key] = str(entry_id)
        archive_hash = str(entry.get("sha256", ""))
        if not HASH_RE.fullmatch(archive_hash):
            errors.append(f"{label}.sha256 must be a SHA-256 digest")
        else:
            hash_key = archive_hash.upper()
            if hash_key in archive_hashes:
                errors.append(
                    f"duplicate archive sha256: {archive_hash} "
                    f"({archive_hashes[hash_key]} and {entry_id})"
                )
            else:
                archive_hashes[hash_key] = str(entry_id)
        for field in ("sizeBytes", "fileCount"):
            if not isinstance(entry.get(field), int) or entry[field] < 1:
                errors.append(f"{label}.{field} must be positive")
        if isinstance(entry.get("sizeBytes"), int) and entry["sizeBytes"] > MAX_TEXTURE_ARCHIVE_BYTES:
            errors.append(f"{label}.sizeBytes exceeds the application's 4 GiB limit")
        if isinstance(entry.get("fileCount"), int) and entry["fileCount"] > MAX_TEXTURE_FILE_COUNT:
            errors.append(f"{label}.fileCount exceeds the application's 50,000-file limit")
        if not entry.get("authors"):
            errors.append(f"{label}.authors must not be empty")
        for preview in entry.get("previewUrls", []):
            if not valid_https(preview):
                errors.append(f"{label}.previewUrls contains an invalid URL")

    audit_path = ROOT / "catalog-audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("schemaVersion") != 1:
            errors.append("catalog-audit.json schemaVersion must be 1")
        batches = audit.get("batches")
        if not isinstance(batches, list):
            errors.append("catalog-audit.json batches must be an array")
            batches = []
        audit_ids: set[str] = set()
        audit_normalized_hashes: set[str] = set()
        audit_manifest_hashes: set[str] = set()
        audit_content_hashes: set[str] = set()
        for batch_index, batch in enumerate(batches):
            batch_label = f"catalog-audit.batches[{batch_index}]"
            audit_entries = batch.get("entries", [])
            if not isinstance(audit_entries, list) or not audit_entries:
                errors.append(f"{batch_label}.entries must be a non-empty array")
                continue
            for audit_index, audit_entry in enumerate(audit_entries):
                audit_label = f"{batch_label}.entries[{audit_index}]"
                catalog_id = str(audit_entry.get("catalogId", ""))
                catalog_entry = catalog_by_id.get(catalog_id)
                if catalog_entry is None:
                    errors.append(f"{audit_label}.catalogId is missing from textures.json")
                    continue
                if catalog_id in audit_ids:
                    errors.append(f"duplicate audit catalogId: {catalog_id}")
                audit_ids.add(catalog_id)

                hash_fields = (
                    ("sourceSha256", None),
                    ("normalizedSha256", audit_normalized_hashes),
                    ("manifestSha256", audit_manifest_hashes),
                    ("contentSetSha256", audit_content_hashes),
                )
                for field, seen_hashes in hash_fields:
                    value = str(audit_entry.get(field, "")).upper()
                    if not HASH_RE.fullmatch(value):
                        errors.append(f"{audit_label}.{field} must be a SHA-256 digest")
                    elif seen_hashes is not None:
                        if value in seen_hashes:
                            errors.append(f"duplicate audit {field}: {value}")
                        seen_hashes.add(value)

                normalized_hash = str(audit_entry.get("normalizedSha256", "")).upper()
                if normalized_hash != str(catalog_entry.get("sha256", "")).upper():
                    errors.append(f"{audit_label}.normalizedSha256 does not match textures.json")
                expected_asset = unquote(
                    urlparse(str(catalog_entry.get("downloadUrl", ""))).path.rsplit("/", 1)[-1]
                )
                if audit_entry.get("assetName") != expected_asset:
                    errors.append(f"{audit_label}.assetName does not match downloadUrl")
                for compared_id in audit_entry.get("comparedAgainst", []):
                    if compared_id not in catalog_by_id:
                        errors.append(
                            f"{audit_label}.comparedAgainst references unknown id: "
                            f"{compared_id}"
                        )
                variant_evidence = audit_entry.get("sourceVariantEvidence", [])
                if not isinstance(variant_evidence, list):
                    errors.append(f"{audit_label}.sourceVariantEvidence must be an array")
                    continue
                for evidence_index, evidence in enumerate(variant_evidence):
                    evidence_label = (
                        f"{audit_label}.sourceVariantEvidence[{evidence_index}]"
                    )
                    if not isinstance(evidence, dict):
                        errors.append(f"{evidence_label} must be an object")
                        continue
                    if not str(evidence.get("label", "")).strip():
                        errors.append(f"{evidence_label}.label must be non-empty text")
                    if not valid_https(evidence.get("sourceUrl")):
                        errors.append(f"{evidence_label}.sourceUrl must be an HTTPS URL")
                    for field in ("manifestSha256", "contentSetSha256"):
                        value = str(evidence.get(field, "")).upper()
                        if not HASH_RE.fullmatch(value):
                            errors.append(f"{evidence_label}.{field} must be a SHA-256 digest")
                    if evidence.get("relationToPublished") not in {"exact", "different"}:
                        errors.append(
                            f"{evidence_label}.relationToPublished must be exact or different"
                        )
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Catalog valid: {len(entries)} entries")


if __name__ == "__main__":
    main()
