#!/usr/bin/env python3
from __future__ import annotations

import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from prepare_pack import PackError, compare, prepare, validate


def png(width: int = 2, height: int = 3) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    raw = b"\x00" + (b"\x00\x00\x00\xff" * width)
    idat_data = zlib.compress(raw * height)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data
    idat += struct.pack(">I", zlib.crc32(b"IDAT" + idat_data))
    iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return signature + ihdr + idat + iend


class PreparePackTest(unittest.TestCase):
    def test_normalizes_serial_and_replacements_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("wrapper/SLUS-12345/replacements/ui/menu.PNG", png())
                archive.writestr("notes.txt", "not shipped")

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    ["replacements/ui/menu.PNG"],
                )
            self.assertEqual(validate(output), summary)

    def test_normalizes_legacy_serial_and_textures_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            output = root / "output.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("wrapper/SLUS-12345/textures/ui/menu.PNG", png())

            summary = prepare(source, output, strip_components=0)

            self.assertEqual(summary.fileCount, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    [entry.filename for entry in archive.infolist()],
                    ["replacements/ui/menu.PNG"],
                )

    def test_rejects_duplicate_normalized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("SLUS-12345/replacements/ui/menu.png", png())
                archive.writestr("replacements/UI/MENU.PNG", png())

            with self.assertRaises(PackError):
                prepare(source, root / "output.zip", strip_components=0)

    def test_rejects_invalid_texture_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("replacements/fake.png", b"not a png")

            with self.assertRaises(PackError):
                prepare(source, root / "output.zip", strip_components=0)

    def test_compare_detects_repacked_duplicate_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            left = root / "left.zip"
            right = root / "right.zip"
            with zipfile.ZipFile(left, "w") as archive:
                archive.writestr("replacements/ui/menu.png", png())
            with zipfile.ZipFile(right, "w") as archive:
                archive.writestr("replacements/renamed/menu.png", png())

            result = compare(left, right)

            self.assertFalse(result.exactManifestMatch)
            self.assertTrue(result.exactContentSetMatch)
            self.assertEqual(result.sharedFileContents, 1)


if __name__ == "__main__":
    unittest.main()
