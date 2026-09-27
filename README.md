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

The current catalog contains **746 verified texture packs** covering **621
regional game serials** and **3,119,501 replacement texture files**. These
totals come from the published `textures.json` catalog. Archives are inspected
before publication; source-only projects, screenshots and emulator-incompatible
dumps are not listed as downloadable packs. Multipart archives count as one
pack in the catalog but as multiple assets in a GitHub release. Distinct
same-game variants are listed only after source and content comparison.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a pack.
