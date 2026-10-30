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
| `office-unified.png` | Unified floor background, palette-quantized with alpha | `office-unified-artwork.prompt.txt` |
| `sources/office-modern.png` | Preserved generated modern office, 1536 x 1024 RGBA | `office-modern-artwork.prompt.txt` |
| `office-modern.png` | Base office floor with 20 desks, two meeting rooms, and a Fika area | `office-modern-artwork.prompt.txt` |
| `office-fika-spacing.png` | Edited source for the bounded Fika high-table region, with four visible stools | `fika-spacing-edit.prompt.txt`, `fika-spacing-edit-02.prompt.txt` |
| `office-meeting-open.png` | Source for the meeting perimeter, twelve chairs, and two presentation displays | `meeting-open.prompt.txt` |
| `office-meeting-divider.png` | Bounded divider and lower wall-mounted presentation display | `meeting-divider.prompt.txt`, `meeting-divider-02.prompt.txt` |
| `office-meeting-av.png` | Two compact tabletop touch controllers and two camera/microphone bars | `meeting-av.prompt.txt`, `meeting-av-02.prompt.txt`, `meeting-av-03.prompt.txt` |
| `seated-lower-parts.png` | Twelve lower-body frames: six front and six rear | `seated-lower-parts.prompt.txt` |
| `high-stool-poses.png` | Eighteen high-stool frames: six front, six rear, and six side | `high-stool-poses.prompt.txt` |
| `employees.png` | Employee atlas: standing (also walking toward the viewer), seated front, seated rear | `character-artwork.prompt.txt` |
| `sleeping.png` | Reclining Employee atlas | `character-artwork.prompt.txt` |
| `coffee-standing.png` | Rear-facing standing Employee atlas (coffee counter, walking away from the viewer) | `character-artwork.prompt.txt` |
| `cats.png` | Cat atlas | `character-artwork.prompt.txt` |
| `employees-varied.png` | Additional appearances of `employees.png` | `employee-appearance.prompt.txt` |
| `sleeping-varied.png` | Additional appearances of `sleeping.png` | `employee-appearance.prompt.txt` |
| `coffee-standing-varied.png` | Additional appearances of `coffee-standing.png` | `employee-appearance.prompt.txt` |

## Storage format

- `office-modern.png`, `seated-lower-parts.png`, and `high-stool-poses.png` retain the generated RGBA bytes. Their dimensions and SHA-256 values are recorded in `office-modern-assets.json`.
- `office-fika-spacing.png`, `office-meeting-open.png`, `office-meeting-divider.png`, and `office-meeting-av.png` retain their generated RGBA bytes. Their corresponding `*-assets.json` files record generation inputs and SHA-256 values.
- Remaining runtime PNG assets use palette quantization with alpha and lossless optimization.
- Dimensions and atlas layouts match the generated originals; sprite coordinates in `sprites.js`, `seated-poses.js`, and `furniture.js` depend on them.

## Code-drawn overlays

Some decoration is drawn in code as SVG over `office-modern.png` at runtime, not generated artwork, and is not stored as PNG:

- `decor.js`: pixel-grid paintings clipped inside two measured wall frames. The background supplies flowers and corner plants. Choices are deterministic per Branch id. They contain no text or logos.
- `mugs.js` and `sprites.js`: mugs, glasses, cans, books, phones, and the Contractor hard hat.
- `lounge.js`: non-verbal speech-bubble glyphs in the lounge and meeting room.
- `presentations.js`: anonymous presentation slides clipped inside the two painted monitor frames. Background, foreground furniture, and walking masks share the current slide. `meeting-screens-annotations.json` records the measured screen corners.
- `desktops.js`: anonymous code, browser, chart, and terminal views inside all 20 desk monitor frames. Each display changes independently every 8 to 15 seconds without consecutive repeats. A `limited` colleague's desk stays dark until that state ends. Reduced motion, hidden offices or pages, and replay suspend changes. `desk-screens.js` stores the corners measured in `desk-screens-annotations.json`; furniture and walking masks share each display's current view.

Overlay and contact coordinates use the original office and its bounded artwork edits. `office-modern-data.js` stores source-pixel measurements, and `office-layout.js` maps them to runtime geometry. `layout.js` shares artwork dimensions and actor metrics with placement, gestures, occlusion, and walking. Changing the background requires re-measuring seat anchors, contacts, routes, frame corners, and window polygons.

## Preserved unified artwork

The D12 raw source is `docs/design/sources/office-unified.png`, SHA-256 `f52a6e68745e0008c74ea1bf85117e1cac4c4e3a010296e13bf40af96a4864b2`. The original output is 1536 x 1024 RGBA. Generation and all three edit requests, reference identities and output hashes are preserved in `office-unified-artwork.prompt.txt`. Its selected layout contains 20 workstations, six meeting chairs, three Fika places and one bed. The owner permits its existing approximately 0.8 percent internal transparency. The stored `office-unified.png` uses 256-entry FASTOCTREE palette quantization without dithering (Pillow 11.1.0), preserving dimensions and indexed alpha. Its SHA-256 is `50d94568c2e853a8c42658b4711f832b4fbcf0889edcc7de2082690a6973e679`. The raw source remains byte-for-byte intact; palette conversion is a storage operation rather than an image correction. `office.png` and all original atlases remain available.

Its annotations retain 30 seat anchors, 82 contact outlines, 36 foreground surfaces, 13 window polygons, and eight painting frames. Actors use 3.2 percent artwork width and a logical SVG foot reference at y=42.32. Image and atlas annotations remain in `tests/browser/fixtures/unified-image-annotations.json` for native-sprite checks. The modern-office annotations below govern active floor routing and placement.

## Modern office geometry and poses

The runtime and preserved raw `office-modern.png` are byte-identical, with SHA-256 `329fdfd71eeafdb3369d116609ca23d1feb599fa0b689b59531b8efbc6f5bd04`. Exact edit prompts, atlas dimensions, reference hashes, and output hashes are in `office-modern-assets.json`. The original unified source and atlases remain available.

The floor contains 20 desks in areas of 4, 4, 4, and 8; two six-chair meeting areas; two eight-chair Fika tables; two three-person sofas; and three two-stool high tables. It contains no bed. The entrance is between the sofas and Fika. The kitchen has two coffee machines, water, a sink, a microwave, and a refrigerator.

`office-modern-data.js` records source-pixel measurements. `office-modern-graph.js` supplies 215 nodes and 214 links, including each chair approach, the entrance, counter, six waiting places, and cat destinations. `office-layout.js` maps the measurements to runtime seat identities. Independent image annotations are retained in `tests/browser/fixtures/modern-image-annotations.json`; native SVG geometry checks compare actual shipped routes against those annotations.

`seated.js` preserves native heads, torsos, props, working hands, and source image proportions. Complete figures scale uniformly around their hip anchors; floor and footrest annotations do not stretch individual body parts. The high-stool atlas has six base appearances in three directions. Foreground chair backs and monitors cover the corresponding source pixels; far-side table edges clip seated bodies. Moving figures have a separate furniture mask. Feet hidden by furniture remain outside direct visual verification.

## Fika high-table artwork composition

The two high tables beside the kitchen have four separate stools, two per table. Their four runtime seats remain `fika.24` through `fika.27`. The office retains all 60 places.

`layout.js` clips `office-fika-spacing.png` to the source rectangle `[1034, 672, 345, 184]`. This edit affects only that rectangle; the meeting edit below has its own measured region. Furniture foreground layers and walking masks use the same image composition. The original office and character PNGs retain their bytes and dimensions.

`fika-spacing-assets.json` records both built-in OpenAI image edits, prompt hashes, and the selected image hash. `fika-spacing-annotations.json` records the four visible cushions, hip registration, footrests, and furniture contacts. The floor graph preserves unaffected route points and provides access to each relocated stool.

## Meeting area artwork composition

Two six-chair meeting areas sit beside the perimeter windows. A solid divider separates them and carries the lower presentation display. The upper area's solid left wall carries its display. Both areas retain separate Project assignments, their table positions, and all twelve chair coordinates. The displays have no floor stands or drawer cabinets.

`layout.js` applies `office-meeting-open.png` inside the polygon recorded in `meeting-open-annotations.json`. It applies `office-meeting-divider.png` above that source, within the measured wall and former floor-stand region in `meeting-divider-annotations.json`. Each edit clips directly in source coordinates. Foreground furniture layers and walking masks share this composition, with distinct SVG clip identities.

Pixels outside the approved Fika and meeting regions come from the original office. An empty office dims the complete composed scene once, with uniform opacity across original and edited regions.

`meeting-open-assets.json` and `meeting-divider-assets.json` record generation inputs, exact prompt hashes, and source image hashes. Their annotation files record the floor outline, chair coordinates, table edges, wall faces and contacts, and perimeter glazing. The divider annotations govern the effective wall and glazing geometry. Night, daylight, and weather effects exclude both solid walls. Painting overlays and lamps follow the retained furniture and walls.

Each meeting table has one compact touch controller, and each wall display has a camera/microphone bar above it. `layout.js` clips `office-meeting-av.png` to four rectangles recorded in `meeting-av-annotations.json`. The composition preserves the tables, all twelve chairs, and floor routes. `meeting-av-assets.json` records the three image edits and selected source. These devices are decorative artwork with no Zoom connection, recording, or device controls.
