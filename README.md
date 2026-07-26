# EmuCoreX Texture Catalog

Curated texture-pack catalog consumed by the EmuCoreX texture manager.

The Git history contains metadata only. Texture archives stay in the original
author's GitHub Releases or, when redistribution is explicitly allowed, in this
repository's Releases. Git LFS must not be used.

## Files

- `textures.json` - production catalog used by EmuCoreX.
- `catalog-audit.json` - persistent source and content fingerprints for
  published batches and duplicate prevention.
- `schemas/texture-catalog.schema.json` - public format contract.
- `scripts/validate_catalog.py` - dependency-free validation.
- `scripts/prepare_pack.py` - safe normalization, inspection and comparison.

Every pack keeps its original author, credits, source link, immutable download
URL, archive size, SHA-256 digest, and supported game serials.

The current catalog contains 83 verified packs covering 100 regional game
serials and 318,622 replacement texture files. Archives are inspected
before publication; source-only projects, screenshots and emulator-incompatible
dumps are not listed as downloadable packs.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a pack.
