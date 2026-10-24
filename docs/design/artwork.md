# Artwork

## Provenance

- Artwork in `packages/agentville/hq/web/*.png` was generated with OpenAI image generation.
- Generation inputs are recorded in `docs/design/*.prompt.txt`.
- No third-party or brand assets are included.
- Distributed under the repository license (Apache-2.0). See `NOTICE`.

## Assets

| File | Content | Generation input |
|---|---|---|
| `office.png` | Original office floor background | `office-artwork.prompt.txt` |
| `sources/office-unified.png` | Preserved original unified office, 1536 x 1024 RGBA | `office-unified-artwork.prompt.txt` |
| `office-unified.png` | Runtime single-floor background, palette-quantized with alpha | `office-unified-artwork.prompt.txt` |
| `employees.png` | Employee atlas: standing (also walking toward the viewer), seated front, seated rear | `character-artwork.prompt.txt` |
| `sleeping.png` | Reclining Employee atlas | `character-artwork.prompt.txt` |
| `coffee-standing.png` | Rear-facing standing Employee atlas (coffee counter, walking away from the viewer) | `character-artwork.prompt.txt` |
| `cats.png` | Cat atlas | `character-artwork.prompt.txt` |
| `employees-varied.png` | Additional appearances of `employees.png` | `employee-appearance.prompt.txt` |
| `sleeping-varied.png` | Additional appearances of `sleeping.png` | `employee-appearance.prompt.txt` |
| `coffee-standing-varied.png` | Additional appearances of `coffee-standing.png` | `employee-appearance.prompt.txt` |

## Storage format

- Palette-quantized PNG with alpha, optimized losslessly afterward.
- Dimensions and atlas layouts match the generated originals; sprite coordinates in `sprites.js` and `furniture.js` depend on them.

## Code-drawn overlays

Some decoration is drawn in code as SVG over `office-unified.png` at runtime, not generated artwork, and is not stored as PNG:

- `decor.js`: pixel-grid paintings clipped inside eight measured wall frames. The background supplies all four flower arrangements. Choices are deterministic per Branch id. They contain no text or logos.
- `mugs.js` and `sprites.js`: mugs, glasses, cans, books, phones, and the Contractor hard hat.
- `lounge.js`: non-verbal speech-bubble glyphs in the lounge and meeting room.

Overlay and contact coordinates are measured against `office-unified.png` and centralized in `office-layout.js`. `layout.js` shares artwork dimensions and actor metrics with placement, gestures, occlusion, and walking. Changing the background requires re-measuring seat anchors, contacts, routes, frame corners, and window polygons.

## Unified source and runtime asset

The D12 raw source is `docs/design/sources/office-unified.png`, SHA-256 `f52a6e68745e0008c74ea1bf85117e1cac4c4e3a010296e13bf40af96a4864b2`. The original output is 1536 x 1024 RGBA. Generation and all three edit requests, reference identities and output hashes are preserved in `office-unified-artwork.prompt.txt`. Its selected layout contains 20 workstations, six meeting chairs, three Fika places and one bed. The owner permits its existing approximately 0.8 percent internal transparency. The runtime uses 256-entry FASTOCTREE palette quantization without dithering (Pillow 11.1.0), preserving dimensions and indexed alpha. Its SHA-256 is `50d94568c2e853a8c42658b4711f832b4fbcf0889edcc7de2082690a6973e679`. The raw source remains byte-for-byte intact; palette conversion is a storage operation rather than an image correction. `office.png` and all original atlases remain available.

The measured layout uses 30 seat anchors, 82 contact outlines, 36 foreground surfaces, 13 window polygons, and eight painting frames. Actors use 3.2 percent artwork width and a logical SVG foot reference at y=42.32. Independent image and atlas annotations are retained in `tests/browser/fixtures/unified-image-annotations.json`; Browser checks compare actual routes and rendering with those annotations. Per-seat visual acceptance and current verification status belong to `docs/milestone-0.4.0.md`.
