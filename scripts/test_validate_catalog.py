#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_catalog


def entry(entry_id: str, *, url: str, digest: str) -> dict[str, object]:
    return {
        "id": entry_id,
        "name": entry_id,
        "gameTitle": "Test Game",
        "serials": ["SLUS-12345"],
        "version": "1",
        "authors": ["Test Author"],
        "downloadUrl": url,
        "sourceUrl": "https://example.com/source",
        "sizeBytes": 1,
        "sha256": digest,
        "fileCount": 1,
    }


class ValidateCatalogTest(unittest.TestCase):
    def run_catalog(self, entries: list[dict[str, object]]) -> str:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "textures.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "generatedAt": "2026-01-01T00:00:00Z",
                        "entries": entries,
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(validate_catalog, "ROOT", root):
                with self.assertRaises(SystemExit) as raised:
                    with contextlib.redirect_stdout(io.StringIO()):
                        validate_catalog.main()
            return str(raised.exception)

    def test_rejects_duplicate_archive_and_url(self) -> None:
        digest = "A" * 64
        url = "https://example.com/pack.zip"
        message = self.run_catalog(
            [
                entry("first", url=url, digest=digest),
                entry("second", url=url, digest=digest),
            ]
        )

        self.assertIn("duplicate downloadUrl", message)
        self.assertIn("duplicate archive sha256", message)


if __name__ == "__main__":
    unittest.main()
