# Artwork

## Provenance

- Artwork in `packages/agentville/hq/web/*.png` was generated with OpenAI image generation.
- Generation inputs are recorded in `docs/design/*.prompt.txt`.
- No third-party or brand assets are included.
- Distributed under the repository license (Apache-2.0). See `NOTICE`.

## Assets

| File | Content | Generation input |
|---|---|---|
| `office.png` | Office floor background | `office-artwork.prompt.txt` |
| `employees.png` | Employee atlas: standing, seated front, seated rear | `character-artwork.prompt.txt` |
| `sleeping.png` | Reclining Employee atlas | `character-artwork.prompt.txt` |
| `coffee-standing.png` | Rear-facing standing Employee atlas | `character-artwork.prompt.txt` |
| `cats.png` | Cat atlas | `character-artwork.prompt.txt` |
| `employees-varied.png` | Additional appearances of `employees.png` | `employee-appearance.prompt.txt` |
| `sleeping-varied.png` | Additional appearances of `sleeping.png` | `employee-appearance.prompt.txt` |
| `coffee-standing-varied.png` | Additional appearances of `coffee-standing.png` | `employee-appearance.prompt.txt` |

## Storage format

- Palette-quantized PNG with alpha, optimized losslessly afterward.
- Dimensions and atlas layouts match the generated originals; sprite coordinates in `sprites.js` and `furniture.js` depend on them.
