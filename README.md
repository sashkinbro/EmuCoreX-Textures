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
- `scripts/split_pack.py` - deterministic binary splitting for normalized ZIPs
  that exceed GitHub's per-asset limit.
- `scripts/safe_extract_7z.py` - guarded integrity testing and extraction of
  public 7z sources.
- `scripts/register_batch.py` - atomic ten-pack catalog and audit registration.

Every pack keeps its original author, credits, source link, immutable download
URL or multipart URLs, archive size, SHA-256 digest, and supported game serials.

The current catalog contains 203 verified packs covering 220 regional game
serials and 773,778 replacement texture files. Archives are inspected
before publication; source-only projects, screenshots and emulator-incompatible
dumps are not listed as downloadable packs.

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a pack.
