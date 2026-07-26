#!/usr/bin/env python3
"""Register a verified local batch in textures.json and catalog-audit.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from prepare_pack import PackError, validate


class RegistrationError(ValueError):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def pretty_json(
    value: Any,
    level: int = 0,
    compact_scalar_keys: frozenset[str] = frozenset(),
    current_key: str | None = None,
) -> str:
    padding = "  " * level
    child_padding = "  " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return padding + "{}"
        lines = []
        for key, item in value.items():
            rendered = pretty_json(
                item, level + 1, compact_scalar_keys, current_key=key
            )
            lines.append(
                child_padding
                + json.dumps(key, ensure_ascii=False)
                + ": "
                + rendered[len(child_padding) :]
            )
        return padding + "{\n" + ",\n".join(lines) + "\n" + padding + "}"
    if isinstance(value, list):
        if not value:
            return padding + "[]"
        if current_key in compact_scalar_keys and all(
            not isinstance(item, (dict, list)) for item in value
        ):
            return padding + json.dumps(
                value, ensure_ascii=False, separators=(", ", ": ")
            )
        return (
            padding
            + "[\n"
            + ",\n".join(
                pretty_json(item, level + 1, compact_scalar_keys) for item in value
            )
            + "\n"
            + padding
            + "]"
        )
    return padding + json.dumps(value, ensure_ascii=False)


def write_json_atomic(
    path: Path,
    value: Any,
    *,
    compact_scalar_keys: frozenset[str] = frozenset(),
) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(pretty_json(value, compact_scalar_keys=compact_scalar_keys))
        stream.write("\n")
    os.replace(temporary, path)


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistrationError(f"{label} must be non-empty text")
    return value.strip()


def provenance_keys(
    source_url: str,
    serials: Any,
    authors: Any,
) -> set[tuple[str, str, str]]:
    if not isinstance(serials, list) or not serials or not all(
        isinstance(serial, str) and serial.strip() for serial in serials
    ):
        raise RegistrationError("catalog.serials must be non-empty text entries")
    if not isinstance(authors, list) or not authors or not all(
        isinstance(author, str) and author.strip() for author in authors
    ):
        raise RegistrationError("catalog.authors must be non-empty text entries")
    normalized_url = source_url.strip().casefold()
    return {
        (normalized_url, serial.strip().upper(), author.strip().casefold())
        for serial in serials
        for author in authors
    }


def register(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = load_json(args.catalog)
    audit = load_json(args.audit)
    manifest = load_json(args.manifest)
    if not isinstance(manifest, list) or len(manifest) != args.expected_count:
        raise RegistrationError(
            f"manifest must contain exactly {args.expected_count} entries"
        )

    catalog_entries = catalog.get("entries")
    audit_batches = audit.get("batches")
    if not isinstance(catalog_entries, list) or not isinstance(audit_batches, list):
        raise RegistrationError("catalog or audit has an unsupported structure")

    existing_ids = {entry["id"] for entry in catalog_entries}
    existing_urls = {entry["downloadUrl"] for entry in catalog_entries}
    existing_archive_hashes = {entry["sha256"].upper() for entry in catalog_entries}
    existing_provenance_keys: set[tuple[str, str, str]] = set()
    for entry in catalog_entries:
        existing_provenance_keys.update(
            provenance_keys(
                require_text(entry.get("sourceUrl"), "catalog.sourceUrl"),
                entry.get("serials"),
                entry.get("authors"),
            )
        )
    # Older catalog entries predate the audit ledger and may store an upstream
    # archive verbatim. Treat their published digest as a source digest too so
    # renaming and re-normalizing the same public artifact cannot bypass the
    # duplicate check.
    existing_source_hashes: set[str] = set(existing_archive_hashes)
    existing_manifest_hashes: set[str] = set()
    existing_content_hashes: set[str] = set()
    for batch in audit_batches:
        if batch.get("id") == args.batch_id:
            raise RegistrationError(f"audit batch already exists: {args.batch_id}")
        for entry in batch.get("entries", []):
            existing_source_hashes.add(entry["sourceSha256"].upper())
            existing_manifest_hashes.add(entry["manifestSha256"].upper())
            existing_content_hashes.add(entry["contentSetSha256"].upper())

    new_entries: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    for index, item in enumerate(manifest):
        label = f"manifest[{index}]"
        slug = require_text(item.get("slug"), f"{label}.slug")
        source_file = require_text(item.get("sourceFile"), f"{label}.sourceFile")
        asset_name = require_text(item.get("assetName"), f"{label}.assetName")
        catalog_fields = item.get("catalog")
        if not isinstance(catalog_fields, dict):
            raise RegistrationError(f"{label}.catalog must be an object")

        catalog_id = require_text(catalog_fields.get("id"), f"{label}.catalog.id")
        source_url = require_text(
            catalog_fields.get("sourceUrl"), f"{label}.catalog.sourceUrl"
        )
        candidate_provenance = provenance_keys(
            source_url,
            catalog_fields.get("serials"),
            catalog_fields.get("authors"),
        )
        provenance_overlap = candidate_provenance & existing_provenance_keys
        variant_evidence = item.get("sourceVariantEvidence")
        if provenance_overlap and not variant_evidence:
            raise RegistrationError(
                f"duplicate source/serial/author provenance: {catalog_id}; "
                "provide sourceVariantEvidence only for a verified distinct variant"
            )
        if variant_evidence is not None:
            if not isinstance(variant_evidence, list) or not variant_evidence:
                raise RegistrationError(
                    f"{label}.sourceVariantEvidence must be a non-empty array"
                )
        source_path = args.source_dir / source_file
        archive_path = args.ready_dir / asset_name
        if not source_path.is_file():
            raise RegistrationError(f"source artifact is missing: {source_path}")
        if not archive_path.is_file():
            raise RegistrationError(f"normalized asset is missing: {archive_path}")
        expected_source_bytes = item.get("expectedSourceBytes")
        if source_path.stat().st_size != expected_source_bytes:
            raise RegistrationError(f"source size mismatch: {source_file}")

        source_sha256 = sha256_file(source_path)
        summary = validate(archive_path)
        download_url = (
            f"https://github.com/{args.repository}/releases/download/"
            f"{args.release_tag}/{asset_name}"
        )
        if catalog_id in existing_ids:
            raise RegistrationError(f"duplicate catalog id: {catalog_id}")
        if download_url in existing_urls:
            raise RegistrationError(f"duplicate download URL: {download_url}")
        if summary.sha256 in existing_archive_hashes:
            raise RegistrationError(f"duplicate normalized archive: {asset_name}")
        if source_sha256 in existing_source_hashes:
            raise RegistrationError(f"duplicate source archive: {source_file}")
        if summary.manifestSha256 in existing_manifest_hashes:
            raise RegistrationError(f"duplicate normalized manifest: {asset_name}")
        if summary.contentSetSha256 in existing_content_hashes:
            raise RegistrationError(f"duplicate texture content set: {asset_name}")

        entry = {
            "id": catalog_fields["id"],
            "name": catalog_fields["name"],
            "gameTitle": catalog_fields["gameTitle"],
            "serials": catalog_fields["serials"],
            "version": catalog_fields["version"],
            "authors": catalog_fields["authors"],
            "credits": catalog_fields["credits"],
            "description": catalog_fields["description"],
            "downloadUrl": download_url,
            "sourceUrl": source_url,
            "license": catalog_fields["license"],
            "sizeBytes": summary.sizeBytes,
            "sha256": summary.sha256,
            "fileCount": summary.fileCount,
            "previewUrls": catalog_fields.get("previewUrls", []),
        }
        new_entries.append(entry)
        audit_entries.append(
            {
                "catalogId": catalog_id,
                "sourceArtifact": require_text(
                    item.get("sourceArtifact", source_file),
                    f"{label}.sourceArtifact",
                ),
                "sourceSha256": source_sha256,
                "assetName": asset_name,
                "normalizedSha256": summary.sha256,
                "manifestSha256": summary.manifestSha256,
                "contentSetSha256": summary.contentSetSha256,
                "comparedAgainst": item.get("comparedAgainst", []),
                **(
                    {"sourceVariantEvidence": variant_evidence}
                    if variant_evidence is not None
                    else {}
                ),
            }
        )
        existing_ids.add(catalog_id)
        existing_urls.add(download_url)
        existing_archive_hashes.add(summary.sha256)
        existing_provenance_keys.update(candidate_provenance)
        existing_source_hashes.add(source_sha256)
        existing_manifest_hashes.add(summary.manifestSha256)
        existing_content_hashes.add(summary.contentSetSha256)

    catalog["generatedAt"] = args.verified_at
    catalog_entries.extend(new_entries)
    audit_batches.append(
        {
            "id": args.batch_id,
            "verifiedAt": args.verified_at,
            "releaseTag": args.release_tag,
            "entries": audit_entries,
        }
    )
    return catalog, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--ready-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("textures.json"))
    parser.add_argument("--audit", type=Path, default=Path("catalog-audit.json"))
    parser.add_argument("--repository", default="sashkinbro/EmuCoreX-Textures")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--verified-at", required=True)
    parser.add_argument("--expected-count", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        catalog, audit = register(args)
        if args.write:
            write_json_atomic(
                args.catalog,
                catalog,
                compact_scalar_keys=frozenset({"serials", "authors"}),
            )
            write_json_atomic(args.audit, audit)
        print(
            json.dumps(
                {
                    "entriesBefore": len(catalog["entries"]) - args.expected_count,
                    "entriesAfter": len(catalog["entries"]),
                    "batchId": args.batch_id,
                    "write": args.write,
                },
                indent=2,
            )
        )
        return 0
    except (RegistrationError, PackError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
