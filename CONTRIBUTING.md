# Contributing texture packs

Open a pull request or issue with:

- game title and every supported PS2 serial;
- pack name and version;
- author and complete credits;
- original repository URL;
- direct HTTPS ZIP download URL;
- redistribution license or confirmation that the catalog should link only to
  the author's original asset;
- archive size and SHA-256 digest;
- optional preview image URLs.

Supported archives are ZIP files containing either `SERIAL/replacements/...` or
`replacements/...`. EmuCoreX always installs into the serial selected from the
user's library and rejects unsafe paths, unsupported file types, oversized
entries, and digest mismatches.

Do not add RAR/7z archives and do not mirror content without permission.

Run `python scripts/validate_catalog.py` before opening a pull request.
