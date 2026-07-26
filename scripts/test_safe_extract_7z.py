import unittest

from safe_extract_7z import ArchiveError, parse_slt_listing, safe_archive_path


class SafeArchivePathTests(unittest.TestCase):
    def test_accepts_relative_texture_path(self):
        self.assertEqual(
            safe_archive_path(r"SLUS-20090\replacements\abc.png").as_posix(),
            "SLUS-20090/replacements/abc.png",
        )

    def test_rejects_traversal_and_absolute_paths(self):
        for candidate in ("../evil.png", r"C:\evil.png", "/evil.png", r"\\host\share"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ArchiveError):
                    safe_archive_path(candidate)


class SltListingTests(unittest.TestCase):
    def test_counts_regular_files(self):
        listing = (
            "Path = SLUS-20090\nFolder = +\nSize = 0\n\n"
            "Path = SLUS-20090/replacements/a.png\nSize = 12\nAttributes = A\n"
        )
        self.assertEqual(parse_slt_listing(listing), (1, 12))

    def test_rejects_encrypted_or_link_entries(self):
        for extra in ("Encrypted = +", "Symbolic Link = target"):
            listing = f"Path = replacements/a.png\nSize = 12\n{extra}\n"
            with self.subTest(extra=extra):
                with self.assertRaises(ArchiveError):
                    parse_slt_listing(listing)


if __name__ == "__main__":
    unittest.main()
