import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from register_batch import (
    RegistrationError,
    provenance_keys,
    resolve_source_sha256,
    sha256_file,
)


class ProvenanceKeyTests(unittest.TestCase):
    def test_normalizes_url_serial_and_author_case(self):
        left = provenance_keys(
            "HTTPS://EXAMPLE.COM/PACK",
            ["slus-20062"],
            ["FunnyNameXYZ"],
        )
        right = provenance_keys(
            "https://example.com/pack",
            ["SLUS-20062"],
            ["funnynamexyz"],
        )
        self.assertEqual(left, right)

    def test_different_author_or_serial_does_not_overlap(self):
        original = provenance_keys(
            "https://example.com/thread",
            ["SLUS-20062"],
            ["Author A"],
        )
        other_author = provenance_keys(
            "https://example.com/thread",
            ["SLUS-20062"],
            ["Author B"],
        )
        other_serial = provenance_keys(
            "https://example.com/thread",
            ["SLUS-21590"],
            ["Author A"],
        )
        self.assertFalse(original & other_author)
        self.assertFalse(original & other_serial)

    def test_rejects_invalid_serial_list(self):
        with self.assertRaises(RegistrationError):
            provenance_keys("https://example.com/thread", [], ["Author"])


class SourceEvidenceTests(unittest.TestCase):
    def test_uses_verified_digest_when_streamed_source_was_removed(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "streamed-source.7z"
            digest = "A" * 64
            self.assertEqual(resolve_source_sha256(missing, 123, digest), digest)

    def test_checks_declared_digest_when_source_is_present(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.zip"
            source.write_bytes(b"verified source")
            digest = sha256_file(source)
            self.assertEqual(
                resolve_source_sha256(source, source.stat().st_size, digest),
                digest,
            )
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(source, source.stat().st_size, "0" * 64)

    def test_missing_source_requires_a_valid_digest(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.zip"
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(missing, 123, None)
            with self.assertRaises(RegistrationError):
                resolve_source_sha256(missing, 123, "not-a-digest")


if __name__ == "__main__":
    unittest.main()
