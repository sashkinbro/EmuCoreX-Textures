# Contributing texture packs

Open a pull request or issue with:

- game title and every supported PS2 serial;
- pack name and version;
- author and complete credits;
- original source URL and author credit;
- the verified ZIP asset URL in this repository's GitHub Releases;
- original publication terms;
- archive size and SHA-256 digest;
- optional preview image URLs.

Supported archives are ZIP files containing either `SERIAL/replacements/...` or
`replacements/...`. EmuCoreX always installs into the serial selected from the
user's library and rejects unsafe paths, unsupported file types, oversized
entries, and digest mismatches.

Download and inspect the author's full archive. Preserve its original source
and credit in the catalog. Publish only a verified ZIP release asset; RAR and
7z files may be used as sources but are not catalog download formats.

Normalize a downloaded ZIP (or an extracted archive directory) before
publication:

```text
python scripts/prepare_pack.py prepare SOURCE READY.zip
```

For a public 7z source, validate paths, links, encryption, entry counts,
expanded size, and archive integrity before extraction:

```text
python scripts/safe_extract_7z.py SOURCE.7z EXTRACTED \
  --seven-zip PATH/TO/7z
```

The command keeps only PNG/DDS textures, writes a clean `replacements/...`
archive, verifies texture headers and CRCs, enforces the Android install limits,
and prints the exact `sizeBytes`, `sha256`, and `fileCount` catalog fields.
Use `--strip-components N` only after inspecting a source that has extra wrapper
directories without a recognizable serial or `replacements` folder.

If the verified normalized ZIP is 2 GiB or larger, keep that full ZIP locally
for inspection and duplicate fingerprints, then split it into release assets:

```text
python scripts/split_pack.py READY.zip BATCH/ready
```

List the generated asset names in the batch manifest's `assetParts`. Each part
must stay below 2 GiB. The catalog retains the size and SHA-256 of the complete
ZIP plus the URL, size and SHA-256 of every ordered part. EmuCoreX verifies each
part, concatenates them, verifies the complete ZIP, and only then installs it.

For every mirrored batch, append its upstream artifact SHA-256, normalized
archive SHA-256, manifest fingerprint, and content-set fingerprint to
`catalog-audit.json`. The catalog validator rejects repeated download URLs,
archive digests, normalized manifests, and content sets.

After every asset in a reviewed batch has been uploaded and API-verified,
register the batch in the catalog and persistent audit ledger. Publish catalog
updates no later than each group of 50 newly verified packs; smaller interim
updates can make already uploaded packs available in the app sooner:

```text
python scripts/register_batch.py --manifest BATCH/sources.json \
  --source-dir BATCH/source --ready-dir BATCH/ready \
  --release-tag TAG --batch-id YYYY-MM-DD-NNN \
  --verified-at YYYY-MM-DDTHH:MM:SSZ --expected-count N --write
```

Run both validation suites before opening a pull request:

```text
python scripts/prepare_pack.py validate READY.zip
python scripts/prepare_pack.py compare EXISTING.zip CANDIDATE.zip
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py"
```
