# EmuCoreX Texture Catalog

Curated texture-pack catalog consumed by the EmuCoreX texture manager.

The Git history contains metadata only. Texture archives are hosted as assets
in this repository's Releases, with original creators and source pages credited
in the catalog. Git LFS must not be used.

## Files

- `textures.json` - production catalog used by EmuCoreX.
- `catalog-audit.json` - persistent source and content fingerprints for
  published batches and duplicate prevention.
- `schemas/texture-catalog.schema.json` - public format contract.
- `scripts/validate_catalog.py` - dependency-free validation.
- `scripts/prepare_pack.py` - safe normalization, inspection and comparison.
- `scripts/split_pack.py` - deterministic binary splitting for normalized ZIPs
  that exceed GitHub's per-asset limit.
- `scripts/safe_extract_7z.py` - guarded integrity testing and extraction of
  public 7z sources.
- `scripts/register_batch.py` - atomic configurable-size catalog and audit
  registration.

Every pack keeps its original author, credits, source link, immutable download
URL or multipart URLs, archive size, SHA-256 digest, and supported game serials.

The current catalog contains 671 verified packs covering 583 regional game
serials and 2,916,634 replacement texture files. Archives are inspected
before publication; source-only projects, screenshots and emulator-incompatible
dumps are not listed as downloadable packs.

Batch 019 adds 48 content-distinct packs, published as 64 release assets
(including multipart archives) in the existing `texture-catalog-2026-07-22`
release. All assets were checked against their exact sizes and SHA-256 digests.

The latest 50-pack catalog publication adds 161,352 replacement texture files
as 64 verified release assets. It includes distinct same-game variants only
after source and content comparison, and keeps source creators credited.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a pack.
