#!/usr/bin/env python3
"""Normalize and validate texture packs for the EmuCoreX catalog.

The generated archive contains texture files only, rooted at
``replacements/``.  The limits mirror TexturePackRepository and
RemoteContentCatalogRepository in the EmuCoreX Android application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, ContextManager, Iterable, Iterator

TEXTURE_EXTENSIONS = {".png", ".dds"}
SERIAL_RE = re.compile(r"^[A-Z]{4}[-_ ]?\d{5}$", re.IGNORECASE)
MAX_ARCHIVE_ENTRIES = 50_000
MAX_TEXTURE_FILE_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_GITHUB_ASSET_BYTES = 2 * 1024 * 1024 * 1024
SUPPORTED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
COPY_BUFFER_BYTES = 1024 * 1024
FIXED_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class PackError(ValueError):
    pass


@dataclass(frozen=True)
class PackSummary:
    path: str
    sizeBytes: int
    sha256: str
    fileCount: int
    uncompressedBytes: int
    extensions: dict[str, int]
    manifestSha256: str
    contentSetSha256: str


@dataclass(frozen=True)
class PackComparison:
    left: str
    right: str
    leftFileCount: int
    rightFileCount: int
    sharedPaths: int
    identicalFilesAtSharedPaths: int
    sharedFileContents: int
    pathJaccard: float
    contentJaccard: float
    exactManifestMatch: bool
    exactContentSetMatch: bool


@dataclass(frozen=True)
class SourceFile:
    name: str
    size: int
    open_file: Callable[[], ContextManager[BinaryIO]]


def clean_parts(raw_name: str) -> tuple[str, ...]:
    if not raw_name or raw_name.startswith(("/", "\\")):
        raise PackError(f"unsafe archive path: {raw_name!r}")
    normalized = raw_name.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if not parts:
        raise PackError(f"empty archive path: {raw_name!r}")
    if any(part == ".." or ":" in part or "\x00" in part for part in parts):
        raise PackError(f"unsafe archive path: {raw_name!r}")
    return parts


def is_serial(part: str) -> bool:
    return bool(SERIAL_RE.fullmatch(part))


def texture_relative_path(parts: tuple[str, ...], strip_components: int) -> tuple[str, ...]:
    lowered = [part.casefold() for part in parts]
    if "replacements" in lowered:
        start = lowered.index("replacements") + 1
        if start < len(parts) and is_serial(parts[start]):
            start += 1
        relative = parts[start:]
    else:
        serial_index = next((index for index, part in enumerate(parts) if is_serial(part)), None)
        if serial_index is not None:
            start = serial_index + 1
            if start < len(parts) and lowered[start] == "replacements":
                start += 1
            relative = parts[start:]
        else:
            relative = parts

    if strip_components:
        if len(relative) <= strip_components:
            raise PackError(
                f"cannot strip {strip_components} components from {'/'.join(parts)!r}"
            )
        relative = relative[strip_components:]
    if not relative:
        raise PackError(f"texture path has no filename: {'/'.join(parts)!r}")
    return relative


def validate_texture_header(stream: BinaryIO, extension: str, label: str) -> None:
    header = stream.read(32)
    if extension == ".png":
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise PackError(f"invalid PNG signature: {label}")
        if header[12:16] != b"IHDR":
            raise PackError(f"PNG has no IHDR header: {label}")
        width, height = struct.unpack(">II", header[16:24])
    elif extension == ".dds":
        if len(header) < 20 or header[:4] != b"DDS ":
            raise PackError(f"invalid DDS signature: {label}")
        if struct.unpack("<I", header[4:8])[0] != 124:
            raise PackError(f"invalid DDS header size: {label}")
        height, width = struct.unpack("<II", header[12:20])
    else:
        raise PackError(f"unsupported texture type: {label}")
    if width <= 0 or height <= 0:
        raise PackError(f"texture has invalid dimensions: {label}")


def iter_zip_source(archive: zipfile.ZipFile) -> Iterator[SourceFile]:
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.flag_bits & 0x1:
            raise PackError(f"encrypted ZIP entry is unsupported: {info.filename}")
        if info.compress_type not in SUPPORTED_COMPRESSION:
            raise PackError(f"unsupported ZIP compression for {info.filename}")
        yield SourceFile(
            name=info.filename,
            size=info.file_size,
            open_file=lambda info=info: archive.open(info, "r"),
        )


def iter_directory_source(path: Path) -> Iterator[SourceFile]:
    for source in sorted((item for item in path.rglob("*") if item.is_file())):
        relative = source.relative_to(path).as_posix()
        yield SourceFile(
            name=relative,
            size=source.stat().st_size,
            open_file=lambda source=source: source.open("rb"),
        )


@contextmanager
def source_files(path: Path) -> Iterator[Iterable[SourceFile]]:
    if path.is_dir():
        yield iter_directory_source(path)
    elif path.is_file() and path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            yield iter_zip_source(archive)
    else:
        raise PackError("input must be a directory or ZIP archive")


def copy_with_limit(source: BinaryIO, target: BinaryIO, expected_size: int) -> int:
    copied = 0
    while True:
        chunk = source.read(COPY_BUFFER_BYTES)
        if not chunk:
            break
        copied += len(chunk)
        if copied > expected_size or copied > MAX_TEXTURE_FILE_BYTES:
            raise PackError("texture entry exceeded its declared or allowed size")
        target.write(chunk)
    if copied != expected_size:
        raise PackError(f"texture size mismatch: expected {expected_size}, read {copied}")
    return copied


def normalized_sources(
    available_sources: Iterable[SourceFile], strip_components: int
) -> list[tuple[SourceFile, str, str]]:
    normalized: list[tuple[SourceFile, str, str]] = []
    seen: dict[str, str] = {}
    total_bytes = 0
    for source in available_sources:
        parts = clean_parts(source.name)
        extension = PurePosixPath(parts[-1]).suffix.casefold()
        if extension not in TEXTURE_EXTENSIONS:
            continue
        if source.size <= 0:
            raise PackError(f"empty texture file: {source.name}")
        if source.size > MAX_TEXTURE_FILE_BYTES:
            raise PackError(f"texture exceeds 512 MiB: {source.name}")
        relative = texture_relative_path(parts, strip_components)
        output_name = "replacements/" + "/".join(relative)
        output_key = output_name.casefold()
        if output_key in seen:
            raise PackError(
                f"duplicate normalized path: {source.name!r} and {seen[output_key]!r}"
            )
        seen[output_key] = source.name
        total_bytes += source.size
        if total_bytes > MAX_UNCOMPRESSED_BYTES:
            raise PackError("pack exceeds 8 GiB uncompressed")
        normalized.append((source, output_name, extension))
        if len(normalized) > MAX_ARCHIVE_ENTRIES:
            raise PackError("pack exceeds 50,000 texture files")
    if not normalized:
        raise PackError("pack contains no PNG or DDS textures")
    return normalized


def prepare(input_path: Path, output_path: Path, strip_components: int) -> PackSummary:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with source_files(input_path) as available_sources:
            sources = normalized_sources(available_sources, strip_components)
            with tempfile.NamedTemporaryFile(
                prefix=f"{output_path.stem}-",
                suffix=".zip",
                dir=output_path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
            with zipfile.ZipFile(
                temp_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as output:
                for source, output_name, extension in sources:
                    with source.open_file() as input_stream:
                        validate_texture_header(input_stream, extension, source.name)
                    info = zipfile.ZipInfo(output_name, date_time=FIXED_ZIP_TIMESTAMP)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    with source.open_file() as input_stream, output.open(
                        info, "w", force_zip64=True
                    ) as target:
                        copy_with_limit(input_stream, target, source.size)
        if temp_path.stat().st_size >= MAX_GITHUB_ASSET_BYTES:
            raise PackError("normalized ZIP reaches GitHub's 2 GiB per-asset limit")
        shutil.move(str(temp_path), output_path)
        temp_path = None
        return validate(output_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(COPY_BUFFER_BYTES):
            digest.update(chunk)
    return digest.hexdigest().upper()


def digest_records(records: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records):
        digest.update(record.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def inspect(path: Path) -> tuple[PackSummary, dict[str, tuple[int, str]]]:
    if not path.is_file() or path.suffix.casefold() != ".zip":
        raise PackError("pack must be a ZIP file")
    size_bytes = path.stat().st_size
    if size_bytes <= 0 or size_bytes >= MAX_GITHUB_ASSET_BYTES:
        raise PackError("ZIP size must be between 1 byte and 2 GiB")

    seen: set[str] = set()
    extensions: Counter[str] = Counter()
    total_bytes = 0
    file_count = 0
    records: dict[str, tuple[int, str]] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = clean_parts(info.filename)
            if parts[0].casefold() != "replacements" or len(parts) < 2:
                raise PackError(f"entry is not rooted at replacements/: {info.filename}")
            extension = PurePosixPath(parts[-1]).suffix.casefold()
            if extension not in TEXTURE_EXTENSIONS:
                raise PackError(f"unsupported file in normalized ZIP: {info.filename}")
            if info.flag_bits & 0x1:
                raise PackError(f"encrypted ZIP entry is unsupported: {info.filename}")
            if info.compress_type not in SUPPORTED_COMPRESSION:
                raise PackError(f"unsupported ZIP compression for {info.filename}")
            key = "/".join(parts).casefold()
            if key in seen:
                raise PackError(f"duplicate case-insensitive ZIP path: {info.filename}")
            seen.add(key)
            if info.file_size <= 0 or info.file_size > MAX_TEXTURE_FILE_BYTES:
                raise PackError(f"invalid texture size: {info.filename}")
            total_bytes += info.file_size
            file_count += 1
            if file_count > MAX_ARCHIVE_ENTRIES:
                raise PackError("pack exceeds 50,000 texture files")
            if total_bytes > MAX_UNCOMPRESSED_BYTES:
                raise PackError("pack exceeds 8 GiB uncompressed")
            with archive.open(info, "r") as stream:
                validate_texture_header(stream, extension, info.filename)
            texture_digest = hashlib.sha256()
            with archive.open(info, "r") as stream:
                while chunk := stream.read(COPY_BUFFER_BYTES):
                    texture_digest.update(chunk)
            records[key] = (info.file_size, texture_digest.hexdigest().upper())
            extensions[extension.removeprefix(".")] += 1

    if file_count == 0:
        raise PackError("pack contains no texture files")
    manifest_sha256 = digest_records(
        f"{name}\0{size}\0{digest}" for name, (size, digest) in records.items()
    )
    content_set_sha256 = digest_records(
        f"{size}\0{digest}" for size, digest in records.values()
    )
    summary = PackSummary(
        path=str(path.resolve()),
        sizeBytes=size_bytes,
        sha256=sha256_file(path),
        fileCount=file_count,
        uncompressedBytes=total_bytes,
        extensions=dict(sorted(extensions.items())),
        manifestSha256=manifest_sha256,
        contentSetSha256=content_set_sha256,
    )
    return summary, records


def validate(path: Path) -> PackSummary:
    return inspect(path)[0]


def compare(left: Path, right: Path) -> PackComparison:
    left_summary, left_records = inspect(left)
    right_summary, right_records = inspect(right)
    left_paths = set(left_records)
    right_paths = set(right_records)
    shared_paths = left_paths & right_paths
    identical_at_path = sum(
        left_records[path] == right_records[path] for path in shared_paths
    )
    left_contents = Counter(left_records.values())
    right_contents = Counter(right_records.values())
    shared_contents = sum((left_contents & right_contents).values())
    path_union = len(left_paths | right_paths)
    content_union = sum((left_contents | right_contents).values())
    return PackComparison(
        left=left_summary.path,
        right=right_summary.path,
        leftFileCount=left_summary.fileCount,
        rightFileCount=right_summary.fileCount,
        sharedPaths=len(shared_paths),
        identicalFilesAtSharedPaths=identical_at_path,
        sharedFileContents=shared_contents,
        pathJaccard=(len(shared_paths) / path_union) if path_union else 1.0,
        contentJaccard=(shared_contents / content_union) if content_union else 1.0,
        exactManifestMatch=left_summary.manifestSha256 == right_summary.manifestSha256,
        exactContentSetMatch=left_summary.contentSetSha256 == right_summary.contentSetSha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="normalize a directory or ZIP")
    prepare_parser.add_argument("input", type=Path)
    prepare_parser.add_argument("output", type=Path)
    prepare_parser.add_argument(
        "--strip-components",
        type=int,
        default=0,
        help="extra leading components to remove after a recognized pack root",
    )

    validate_parser = subparsers.add_parser("validate", help="validate a normalized ZIP")
    validate_parser.add_argument("archive", type=Path)

    compare_parser = subparsers.add_parser(
        "compare", help="compare two normalized ZIPs for duplicate content"
    )
    compare_parser.add_argument("left", type=Path)
    compare_parser.add_argument("right", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare":
            if args.strip_components < 0:
                raise PackError("--strip-components cannot be negative")
            summary = prepare(args.input.resolve(), args.output.resolve(), args.strip_components)
        elif args.command == "validate":
            summary = validate(args.archive.resolve())
        else:
            summary = compare(args.left.resolve(), args.right.resolve())
    except (PackError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise SystemExit(f"error: {error}") from error
    json.dump(asdict(summary), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
