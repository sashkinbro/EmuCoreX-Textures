#!/usr/bin/env python3
"""Validate an untrusted 7z archive before extracting it with 7-Zip."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_ENTRIES = 50_000
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveSummary:
    file_count: int
    uncompressed_bytes: int
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def filesystem_path(path: Path) -> Path:
    """Return a Windows extended-length path without changing its target."""
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return Path(resolved)
    if resolved.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + resolved[2:])
    return Path("\\\\?\\" + resolved)


def safe_archive_path(raw_path: str) -> PurePosixPath:
    normalized = raw_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not raw_path
        or raw_path.startswith(("/", "\\"))
        or DRIVE_PREFIX.match(raw_path)
        or path.is_absolute()
        or any(part in ("", ".", "..") or ":" in part or "\x00" in part for part in path.parts)
    ):
        raise ArchiveError(f"unsafe archive path: {raw_path!r}")
    return path


def parse_slt_listing(output: str) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for block in re.split(r"\r?\n\r?\n", output.strip()):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                fields[key.strip()] = value
        raw_path = fields.get("Path")
        if not raw_path:
            continue
        safe_archive_path(raw_path)
        if fields.get("Encrypted") == "+":
            raise ArchiveError(f"encrypted entry is unsupported: {raw_path}")
        attributes = fields.get("Attributes", "")
        if "Symbolic Link" in fields or "Hard Link" in fields or "L" in attributes.upper():
            raise ArchiveError(f"link entry is unsupported: {raw_path}")
        is_directory = fields.get("Folder") == "+" or attributes.upper().startswith("D")
        if is_directory:
            continue
        try:
            size = int(fields.get("Size", "0"))
        except ValueError as error:
            raise ArchiveError(f"invalid entry size for {raw_path}") from error
        if size < 0:
            raise ArchiveError(f"invalid entry size for {raw_path}")
        file_count += 1
        total_bytes += size
        if file_count > MAX_ENTRIES:
            raise ArchiveError(f"archive exceeds {MAX_ENTRIES:,} files")
        if total_bytes > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveError("archive exceeds 8 GiB uncompressed")
    if file_count == 0:
        raise ArchiveError("archive contains no files")
    return file_count, total_bytes


def run_7z(executable: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def validate_archive(executable: Path, archive: Path) -> ArchiveSummary:
    archive_sha256 = sha256_file(archive)
    listing = run_7z(executable, ["l", "-slt", "-ba", "-sccUTF-8", str(archive)])
    if listing.returncode != 0:
        raise ArchiveError(f"7-Zip listing failed:\n{listing.stderr or listing.stdout}")
    file_count, total_bytes = parse_slt_listing(listing.stdout)
    test = run_7z(executable, ["t", "-bb0", "-bd", "-sccUTF-8", str(archive)])
    if test.returncode != 0:
        raise ArchiveError(f"7-Zip integrity test failed:\n{test.stderr or test.stdout}")
    if sha256_file(archive) != archive_sha256:
        raise ArchiveError("archive changed during validation")
    return ArchiveSummary(file_count, total_bytes, archive_sha256)


def extract_archive(executable: Path, archive: Path, destination: Path) -> ArchiveSummary:
    destination_fs = filesystem_path(destination)
    if destination_fs.exists() and any(destination_fs.iterdir()):
        raise ArchiveError(f"destination is not empty: {destination}")
    destination_fs.mkdir(parents=True, exist_ok=True)
    summary = validate_archive(executable, archive)
    result = run_7z(
        executable,
        ["x", "-y", "-bb0", "-bd", "-sccUTF-8", f"-o{destination_fs}", str(archive)],
    )
    if result.returncode != 0:
        raise ArchiveError(f"7-Zip extraction failed:\n{result.stderr or result.stdout}")
    if sha256_file(archive) != summary.sha256:
        raise ArchiveError("archive changed during extraction")

    resolved_root = destination_fs.resolve()
    for item in destination_fs.rglob("*"):
        if item.is_symlink():
            raise ArchiveError(f"extracted symbolic link is unsupported: {item}")
        attributes = getattr(item.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if attributes & reparse_flag:
            raise ArchiveError(f"extracted reparse point is unsupported: {item}")
        try:
            item.resolve().relative_to(resolved_root)
        except ValueError as error:
            raise ArchiveError(f"extracted path escaped destination: {item}") from error
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--seven-zip", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = extract_archive(
            args.seven_zip.resolve(), args.archive.resolve(), args.destination.resolve()
        )
    except (ArchiveError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"Verified and extracted {summary.file_count} files, "
        f"{summary.uncompressed_bytes} bytes, sha256={summary.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
