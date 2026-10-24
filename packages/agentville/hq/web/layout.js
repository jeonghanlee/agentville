// Artwork dimensions and actor geometry shared by placement, gestures, occlusion and movement.
export const ARTWORK = { file: "office-unified.png", width: 1536, height: 1024 };
export const ACTOR_WIDTH = 3.2;
export const ACTOR_SCALE = ACTOR_WIDTH / 5;
export const ACTOR_VIEW = { width: 32, height: 43, foot: 42.32, front: .64, back: .78 };
export const RECLINING_WIDTH = 8 * ACTOR_SCALE;
export const CONTRACTOR_WIDTH = 3.5 * ACTOR_SCALE;
export const CAT_WIDTH = 4 * ACTOR_SCALE;
export const PROJECTS_PER_PAGE = 4;
export const WALK_PERIOD = .56;
export const WALK_SPEED = [5.2, 6.4].map((value) => value * ACTOR_SCALE);

export const actorPixels = () => ARTWORK.width * ACTOR_WIDTH / 100;
export const actorHeightPixels = () => actorPixels() * ACTOR_VIEW.height / ACTOR_VIEW.width;
export const pointPercent = ([x,y]) => [x / ARTWORK.width * 100, y / ARTWORK.height * 100];
export const pointPixels = ([x,y]) => [x / 100 * ARTWORK.width, y / 100 * ARTWORK.height];

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
