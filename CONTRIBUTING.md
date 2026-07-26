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

Normalize a downloaded ZIP (or an extracted archive directory) before
publication:

```text
python scripts/prepare_pack.py prepare SOURCE READY.zip
```

The command keeps only PNG/DDS textures, writes a clean `replacements/...`
archive, verifies texture headers and CRCs, enforces the Android install limits,
and prints the exact `sizeBytes`, `sha256`, and `fileCount` catalog fields.
Use `--strip-components N` only after inspecting a source that has extra wrapper
directories without a recognizable serial or `replacements` folder.

For every mirrored batch, append its upstream artifact SHA-256, normalized
archive SHA-256, manifest fingerprint, and content-set fingerprint to
`catalog-audit.json`. The catalog validator rejects repeated download URLs,
archive digests, normalized manifests, and content sets.

Run both validation suites before opening a pull request:

```text
python scripts/prepare_pack.py validate READY.zip
python scripts/prepare_pack.py compare EXISTING.zip CANDIDATE.zip
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py"
```
