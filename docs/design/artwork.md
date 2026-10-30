# Artwork

## Office image

`packages/agentville/hq/web/office-modern.png` is the single 1536 x 1024 office image. It contains the desks, meeting rooms, Fika area, kitchen, lounge, wall pictures, and furniture. Background, foreground furniture, and walking masks use this image. The lounge table contains a book and magazine.

The floor beside the lounge plant contains two cat beds and food and water bowls. The furniture footprints keep employee routes clear of the resting area.

The office contains 20 desks, two six-chair meeting rooms, two eight-chair Fika tables, two three-person sofas, and three two-stool high tables. The kitchen has a dishwasher beside the sink. Each meeting room has a wall display and camera bar. Each meeting table has a decorative touch controller. The equipment does not connect to Zoom or record audio or video.

`office-modern-data.js` records source-pixel measurements. `office-modern-graph.js` supplies routes to chairs, the entrance, counter, waiting places, and cat destinations. `office-layout.js` maps measurements to runtime identities. `tests/browser/fixtures/modern-image-annotations.json` records seat and contact measurements.

## Characters and displays

Employee and cat atlases are separate from the office image. `seated.js` positions complete figures at their measured seats. Foreground furniture and walking masks use the office image to cover figures where appropriate.

`presentations.js` draws changing content within the two painted meeting displays. `desktops.js` draws changing content within the ten desk monitors facing the viewer; the other monitors show their painted backs. `meeting-screens-annotations.json` and `desk-screens-annotations.json` record the screen corners.

`daylight.js` applies light and weather effects over the windows. The left wall frames retain the pictures in the office image. Mugs, speech bubbles, and character props are rendered separately.

## Generation

The office and character artwork uses OpenAI image generation. Generation prompts are recorded in `docs/design/*.prompt.txt`. The office image combines the selected office edits at their original pixel coordinates. No third-party or brand assets are included. Artwork is distributed under the repository license; see `NOTICE`.
