import unittest

from register_batch import RegistrationError, provenance_keys


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


if __name__ == "__main__":
    unittest.main()
