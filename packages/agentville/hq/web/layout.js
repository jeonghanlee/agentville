// Artwork dimensions and actor geometry shared by placement, gestures, occlusion and movement.
import { presentationArtwork } from "./presentations.js";
import { deskArtwork } from "./desktops.js";
export const ARTWORK = { file: "office-modern.png", width: 1536, height: 1024 };
export const ARTWORK_PATCHES = [
  { id: "fika", file: "office-fika-spacing.png", bounds: [1034, 672, 345, 184] },
  { id: "meeting", file: "office-meeting-open.png", bounds: [950, 60, 586, 540],
    polygon: [[950,60],[1118,60],[1536,297],[1536,488],[1340,600],[1030,424],[950,378]] },
  { id: "divider", file: "office-meeting-divider.png", bounds: [1164, 205, 174, 230],
    polygon: [[1164,311],[1325,205],[1338,213],[1338,288],[1237,358],[1237,390],[1219,403],[1220,418],[1224,422],[1224,428],[1213,435],[1194,435],[1185,429],[1185,420],[1190,414],[1190,411],[1172,427],[1172,395],[1164,388]] },
  { id: "av-upper-controller", file: "office-meeting-av.png", bounds: [1133, 229, 23, 19] },
  { id: "av-lower-controller", file: "office-meeting-av.png", bounds: [1325, 364, 23, 19] },
  { id: "av-upper-camera", file: "office-meeting-av.png", bounds: [1026, 103, 43, 35] },
  { id: "av-lower-camera", file: "office-meeting-av.png", bounds: [1237, 249, 48, 35] },
];

// Each measured edit clips its source pixels in every background and furniture layer.
export function artworkPatch(scope = "base", edits = ARTWORK_PATCHES) {
  return edits.map((edit) => {
    const [x, y, width, height] = edit.bounds, id = `${scope}-edit-${edit.id}`;
    const shape = edit.polygon ? `<polygon points="${edit.polygon.map((p) => p.join(",")).join(" ")}"/>`
      : `<rect x="${x}" y="${y}" width="${width}" height="${height}"/>`;
    return `<g data-artwork-edit="${edit.id}"><defs><clipPath id="${id}" clipPathUnits="userSpaceOnUse">${shape}</clipPath></defs>`
      + `<image href="${edit.file}" width="${ARTWORK.width}" height="${ARTWORK.height}" clip-path="url(#${id})"/></g>`;
  }).join("");
}

export function displayArtwork(scope, clips = null) {
  return presentationArtwork(scope) + deskArtwork(scope, clips);
}

export function artworkImages(scope = "base", clips = null, displays = true) {
  return `<image href="${ARTWORK.file}" width="${ARTWORK.width}" height="${ARTWORK.height}"/>` + artworkPatch(scope)
    + (displays ? displayArtwork(scope, clips) : "");
}
export const ACTOR_WIDTH = 3.2;
export const ACTOR_SCALE = ACTOR_WIDTH / 5;
export const ACTOR_VIEW = { width: 32, height: 43, foot: 42.32, front: .64, back: .78 };
export const RECLINING_WIDTH = 8 * ACTOR_SCALE;
export const CONTRACTOR_WIDTH = 3.5 * ACTOR_SCALE;
export const CAT_WIDTH = 4 * ACTOR_SCALE;
export const PROJECTS_PER_PAGE = 4;
export const WALK_PERIOD = .56;
export const WALK_SPEED = [5.2, 6.4].map((value) => value * ACTOR_SCALE);
export const WALK_STRIDE = (WALK_SPEED[0] + WALK_SPEED[1]) / 2 * WALK_PERIOD;

export const actorPixels = () => ARTWORK.width * ACTOR_WIDTH / 100;
export const actorHeightPixels = () => actorPixels() * ACTOR_VIEW.height / ACTOR_VIEW.width;
export const pointPercent = ([x,y]) => [x / ARTWORK.width * 100, y / ARTWORK.height * 100];
export const pointPixels = ([x,y]) => [x / 100 * ARTWORK.width, y / 100 * ARTWORK.height];
export const floorDepth = (y) => Math.round(y / 100 * ARTWORK.height * 10) + 1;

// The logical floor point is inside the soles, rather than the bottom of the atlas viewport.
export function seatedFootOffset(rear) {
  const anchor = (rear ? ACTOR_VIEW.back : ACTOR_VIEW.front) * ACTOR_VIEW.height;
  return (ACTOR_VIEW.foot - anchor) * actorPixels() / ACTOR_VIEW.width / ARTWORK.height * 100;
}

export function applyLayoutMetrics(world) {
  const values = {
    "--actor-width": ACTOR_WIDTH + "%",
    "--reclining-width": RECLINING_WIDTH + "%",
    "--contractor-width": CONTRACTOR_WIDTH + "%",
    "--cat-width": CAT_WIDTH + "%",
    "--foot-translate": -(ACTOR_VIEW.foot / ACTOR_VIEW.height * 100) + "%",
    "--seat-front-translate": -(ACTOR_VIEW.front * 100) + "%",
    "--seat-back-translate": -(ACTOR_VIEW.back * 100) + "%",
    "--walk-period": WALK_PERIOD + "s",
  };
  for (const [name,value] of Object.entries(values)) world.style.setProperty(name,value);
}
