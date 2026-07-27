#!/usr/bin/env python3
"""Split a verified normalized ZIP into GitHub-release-sized binary parts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from prepare_pack import COPY_BUFFER_BYTES, PackError, validate

DEFAULT_PART_BYTES = 1_900_000_000
MAX_GITHUB_ASSET_BYTES = 2 * 1024 * 1024 * 1024


def split_pack(archive: Path, output_dir: Path, part_bytes: int) -> dict[str, object]:
    if part_bytes <= 0 or part_bytes >= MAX_GITHUB_ASSET_BYTES:
        raise PackError("part size must be positive and below GitHub's 2 GiB limit")
    summary = validate(archive)
    output_dir.mkdir(parents=True, exist_ok=True)
    if summary.sizeBytes < MAX_GITHUB_ASSET_BYTES:
        raise PackError("archive is already below GitHub's 2 GiB asset limit")

    part_count = (summary.sizeBytes + part_bytes - 1) // part_bytes
    width = max(3, len(str(part_count)))
    final_paths = [
        output_dir / f"{archive.name}.part{index:0{width}d}"
        for index in range(1, part_count + 1)
    ]
    for path in final_paths:
        if path.exists():
            raise PackError(f"refusing to overwrite existing part: {path.name}")

    temporary_paths: list[Path] = []
    parts: list[dict[str, object]] = []
    whole_digest = hashlib.sha256()
    copied_total = 0
    try:
        with archive.open("rb") as source:
            for final_path in final_paths:
                with tempfile.NamedTemporaryFile(
                    prefix=f"{final_path.name}.",
                    suffix=".tmp",
                    dir=output_dir,
                    delete=False,
                ) as target:
                    temporary_path = Path(target.name)
                    temporary_paths.append(temporary_path)
                    part_digest = hashlib.sha256()
                    copied_part = 0
                    while copied_part < part_bytes:
                        chunk = source.read(
                            min(COPY_BUFFER_BYTES, part_bytes - copied_part)
                        )
                        if not chunk:
                            break
                        target.write(chunk)
                        part_digest.update(chunk)
                        whole_digest.update(chunk)
                        copied_part += len(chunk)
                        copied_total += len(chunk)
                if copied_part <= 0 or copied_part >= MAX_GITHUB_ASSET_BYTES:
                    raise PackError("generated part has an invalid size")
                parts.append(
                    {
                        "assetName": final_path.name,
                        "sizeBytes": copied_part,
                        "sha256": part_digest.hexdigest().upper(),
                    }
                )
            if source.read(1):
                raise PackError("split did not consume the complete archive")
        if copied_total != summary.sizeBytes:
            raise PackError("split size does not match the normalized ZIP")
        if whole_digest.hexdigest().upper() != summary.sha256:
            raise PackError("split digest does not reconstruct the normalized ZIP")
        for temporary_path, final_path in zip(temporary_paths, final_paths):
            os.replace(temporary_path, final_path)
        temporary_paths.clear()
        return {
            "archive": str(archive.resolve()),
            "sizeBytes": summary.sizeBytes,
            "sha256": summary.sha256,
            "parts": parts,
        }
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--part-bytes", type=int, default=DEFAULT_PART_BYTES)
    args = parser.parse_args()
    try:
        result = split_pack(
            args.archive.resolve(),
            args.output_dir.resolve(),
            args.part_bytes,
        )
    except (PackError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
