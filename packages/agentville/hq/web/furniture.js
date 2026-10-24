import { FOOTPRINTS } from "./floor.js";
import { mirroredFacing } from "./seats.js";

import { SURFACES } from "./office-layout.js";
import { ARTWORK, ACTOR_WIDTH, ACTOR_VIEW } from "./layout.js";

// Furniture and actors share floor depth; foreground pixels match the source artwork.
function bounds(polygon, x) {
  const ys = [];
  for (let i = 0, j = polygon.length-1; i < polygon.length; j = i++) {
    const [x1,y1] = polygon[j], [x2,y2] = polygon[i];
    if ((x1 <= x && x <= x2) || (x2 <= x && x <= x1)) ys.push(x1 === x2 ? Math.min(y1,y2) : y1 + (y2-y1) * (x-x1) / (x2-x1));
    if (x1 === x2 && x1 === x) ys.push(Math.max(y1,y2));
  }
  return ys.length ? [Math.min(...ys), Math.max(...ys)] : null;
}

// Percent extents of each piece's pixels and of its footprint, to tell which pieces a walker's sprite can cover.
const EXTENTS = SURFACES.map(({ footprint, shapes }) => {
  const pixels = shapes.flatMap((points) => points.trim().split(/\s+/).map((point) => point.split(",").map(Number)));
  const xs = FOOTPRINTS[footprint].map(([x]) => x);
  return { left: Math.min(...pixels.map(([x]) => x)) / ARTWORK.width * 100, right: Math.max(...pixels.map(([x]) => x)) / ARTWORK.width * 100,
    top: Math.min(...pixels.map(([,y]) => y)) / ARTWORK.height * 100, bottom: Math.max(...pixels.map(([,y]) => y)) / ARTWORK.height * 100,
    from: Math.min(...xs), to: Math.max(...xs) };
});
// The sprite extent ends at the shared logical foot anchor.
const SPRITE = [ACTOR_WIDTH / 2, ACTOR_WIDTH * ARTWORK.width / ARTWORK.height * ACTOR_VIEW.foot / ACTOR_VIEW.width];

// Stacking order of a walker whose feet are at (x, y) percent: in front of pieces whose footprint lies
// behind the feet, behind pieces whose footprint lies in front of them. Beside a piece whose pixels the sprite
// overlaps, the nearest end of its footprint decides.
export function walkerDepth(x, y) {
  let lower = -Infinity, upper = Infinity;
  SURFACES.forEach(({ depth, footprint }, index) => {
    const extent = EXTENTS[index];
    const near = x + SPRITE[0] > extent.left && x - SPRITE[0] < extent.right && y > extent.top && y - SPRITE[1] < extent.bottom;
    const span = bounds(FOOTPRINTS[footprint], x) || (near ? bounds(FOOTPRINTS[footprint], Math.min(Math.max(x, extent.from), extent.to)) : null);
    if (!span) return;
    if (y >= span[1] || (y > span[0] && y > (span[0]+span[1]) / 2)) lower = Math.max(lower, depth+1);
    else upper = Math.min(upper, depth-1);
  });
  const base = Math.floor(y) + 1;
  return lower > upper ? lower : Math.min(Math.max(base, lower), upper);
}

export function mountFurniture(world) {
  for (const { name, depth, shapes } of SURFACES) {
    const layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const id = "furniture-" + name;
    layer.setAttribute("viewBox", `0 0 ${ARTWORK.width} ${ARTWORK.height}`);
    layer.setAttribute("class", "furniture-front");
    layer.setAttribute("aria-hidden", "true");
    layer.dataset.furniture = name;
    layer.style.zIndex = depth;
    layer.innerHTML = '<defs><clipPath id="' + id + '">'
      + shapes.map((points) => '<polygon points="' + points + '"/>').join("")
      + '</clipPath></defs><image href="' + ARTWORK.file + '" width="' + ARTWORK.width + '" height="' + ARTWORK.height + '" clip-path="url(#' + id + ')"/>';
    world.append(layer);
  }
  const outline = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  outline.setAttribute("viewBox",`0 0 ${ARTWORK.width} ${ARTWORK.height}`);
  outline.setAttribute("class","selection-outline");
  outline.setAttribute("aria-hidden","true");
  world.append(outline);
  let previous = "";
  let revision = 0;
  return {
    update() {
      // A hidden office has no floor size; skip until it is shown again.
      const floor = world.getBoundingClientRect();
      if (!floor.width || !floor.height) return;
      const selected = world.querySelector(".agent.selected:not(.filtered)");
      if (!selected) { outline.replaceChildren(); previous = ""; return; }
      const bounds = selected.getBoundingClientRect();
      const signature = [selected.dataset.appearance, bounds.x, bounds.y, bounds.width, selected.style.zIndex].join("|");
      if (signature === previous) return;
      previous = signature;
      const surfaces = SURFACES.filter((surface) => surface.depth > Number(selected.style.zIndex));
      outline.innerHTML = '<defs><clipPath id="selected-hidden-surfaces">'
        + surfaces.flatMap((surface) => surface.shapes).map((points) => '<polygon points="' + points + '"/>').join("")
        + '</clipPath><filter id="selected-silhouette" x="-20%" y="-20%" width="140%" height="140%">'
        + '<feMorphology in="SourceAlpha" operator="dilate" radius="1.5" result="outer"/>'
        + '<feMorphology in="SourceAlpha" operator="erode" radius=".5" result="inner"/>'
        + '<feComposite in="outer" in2="inner" operator="out" result="edge"/>'
        + '<feFlood flood-color="#f9e4a8"/><feComposite in2="edge" operator="in"/></filter></defs>';
      const clone = selected.querySelector(".character").cloneNode(true);
      const ids = new Map();
      clone.querySelectorAll("[id]").forEach((node) => { const id = node.id; node.id = "outline-" + revision + "-" + id; ids.set(id,node.id); });
      clone.querySelectorAll("*").forEach((node) => {
        for (const attr of [...node.attributes]) {
          for (const [id,replacement] of ids) if (attr.value.includes("url(#" + id + ")")) node.setAttribute(attr.name,attr.value.replaceAll("url(#" + id + ")","url(#" + replacement + ")"));
        }
      });
      revision++;
      // Only the character is outlined; state marks and props such as books, mugs, phones, and steam are left out.
      clone.querySelectorAll(".state-symbol, .state-clock, .study-books, .hand-prop, .brewing-steam").forEach((node) => node.remove());
      clone.setAttribute("class","outline-character");
      clone.setAttribute("x",(bounds.x-floor.x)*ARTWORK.width/floor.width);
      clone.setAttribute("y",(bounds.y-floor.y)*ARTWORK.height/floor.height);
      clone.setAttribute("width",bounds.width*ARTWORK.width/floor.width);
      clone.setAttribute("height",bounds.height*ARTWORK.height/floor.height);
      clone.style.removeProperty("transform");
      if (mirroredFacing(selected.dataset.seatFacing) || selected.dataset.coffeeFacing === "left") {
        const mirror = document.createElementNS("http://www.w3.org/2000/svg","g");
        mirror.setAttribute("transform","translate(32 0) scale(-1 1)");
        mirror.append(...clone.childNodes); clone.append(mirror);
      }
      const clip = document.createElementNS("http://www.w3.org/2000/svg","g");
      clip.setAttribute("clip-path","url(#selected-hidden-surfaces)");
      const silhouette = document.createElementNS("http://www.w3.org/2000/svg","g");
      silhouette.setAttribute("filter","url(#selected-silhouette)");
      silhouette.append(clone); clip.append(silhouette); outline.append(clip);
    },
  };
}
