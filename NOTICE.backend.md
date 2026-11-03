# Backend source and asset notice

The backend and tests are original GPL-3.0-only code implementing narrowly ported behavior after source review. No HyDE script is executed or vendored at runtime. Each backend is independent and uses Python standard-library modules and existing system CLI tools only.

## Reviewed HyDE lineage

Repository: https://github.com/HyDE-Project/HyDE

Pinned commit: `fa2fd57afc7203b1b5653d3271f3a57ea3873f97`. Upstream repository license is GNU GPL version 3; this does not determine individual dataset/font/image rights.

- `Configs/.local/lib/hyde/glyph-picker.sh` — SHA-256 `24b868503f144aaf5690b9d2a5d9d25fc197b0fb990ad583cec31d4eab534cb5`
- `Configs/.local/share/hyde/glyph.db` — SHA-256 `6583981226e9ad48276e4ba4411ec75ee136602c2fc632b835b0a22960dd551a`

The donor supplies the glyph-name/copy scenario only. Its Rofi setup, eval/init, process-name killing, recent-history writes and paste behavior were excluded. The 237,195-byte HyDE glyph.db was reviewed but **not redistributed**: its separate mapping provenance was not asserted from the repository GPL license.

## Shipped mapping rights

The v0.3.0 named collections are original name-filtering rules over this unchanged mapping. Favorites/recent/personal collections use new local preference code, not HyDE's history mechanism. No additional donor data, font artwork or network source was added.

`runtime/0.4.1/data/glyphs.tsv` is derived directly from Nerd Fonts root `glyphnames.json`, tag v3.4.0, commit `fa7b859994228a9c8759f99c55a8d31ee92a1b5e`, not copied from HyDE glyph.db. The pinned Nerd Fonts LICENSE explicitly states that source files not in folders with an explicit license use MIT. This root JSON metadata is shipped under that metadata license, **not relicensed as GPL and not represented as font software**. Copyright (c) 2014 Ryan L McIntyre. The full upstream license and MIT notice are included in `runtime/0.4.1/data/LICENSE.nerd-fonts`; immutable source/output hashes and transformation details are in `runtime/0.4.1/data/provenance.json`.

The transformation keeps 10,757 canonical single private-use mappings (237,078 bytes), excludes seven non-private-use mappings, and preserves aliases with distinct canonical IDs. The runtime metadata distribution contains symbol names/codepoints, not font binaries, outlines, SVGs, rendered glyph artwork, brand/logo image assets or wallpapers. The illustrative raster `preview.png` does contain symbols rendered by an installed Nerd Font; it is not part of the mapping metadata. Original project UI/illustrative composition is GPL-3.0-only; the rendered font/component designs retain their separate applicable licenses. The MIT mapping-data license does not relicense those designs, and the preview does not bundle or relicense a font binary. Installing/rendering a font has its own applicable font licenses; the picker does not install one. This is a rights-traced metadata derivative, not a claim to have licensed all constituent font designs.

Tests create synthetic desktop entries, manifests and SQLite databases in fake HOME. The tiny one-pixel raster fixture is test data, not a real application/game asset. Backend action receipts prove literal argv and helper acknowledgement through private executable shims, not live clipboard ownership or actual app/game startup.
