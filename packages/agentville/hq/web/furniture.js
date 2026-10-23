import { FOOTPRINTS } from "./floor.js";
import { mirroredFacing } from "./seats.js";

// Furniture and actors share floor depth; foreground pixels match the room exactly.
// A footprint names the floor contact in floor.js, so moving walkers can be ordered against the piece.
const SURFACES = [
  { name: "studio-desks", depth: 35, footprint: "studio-desk", shapes: [
    "286,297 294,285 367,254 367,231 383,232 427,250 427,242 474,259 474,277 604,318 604,279 654,293 654,311 697,326 697,349 731,357 729,398 686,425 685,478 627,494 443,428 444,373 306,332 306,370 288,365",
  ] },
  { name: "studio-chair-left", depth: 40, footprint: "studio-chair-near-a", shapes: ["344,319 383,331 394,345 399,368 390,386 355,374 346,358"] },
  { name: "studio-chair-right", depth: 46, footprint: "studio-chair-near-b", shapes: ["488,370 531,384 545,399 547,423 535,437 504,424 494,408"] },
  { name: "common-chair-left", depth: 64, footprint: "common-chair-a", shapes: ["163,565 200,579 214,594 216,620 202,635 173,618 166,602"] },
  { name: "common-chair-right", depth: 69, footprint: "common-chair-b", shapes: ["292,615 327,628 340,642 343,668 329,681 299,665 294,649"] },
  { name: "garden-chair-left", depth: 43, footprint: "studio1-chair-a", shapes: ["1102,344 1145,357 1158,370 1167,397 1150,414 1121,399 1107,379"] },
  { name: "garden-chair-right", depth: 49, footprint: "studio1-chair-b", shapes: ["1243,400 1279,413 1292,429 1296,451 1280,469 1250,454 1246,433"] },
  // Lounge walls, counter, and the whole sofa hide walkers in the aisle and behind the sofa; seated occupants stay in front.
  { name: "lounge-walls", depth: 58, footprint: "lounge-walls", shapes: ["685,444 829,387 863,395 1026,446 1026,643 977,651 922,643 774,603 771,641 722,641 685,635"] },
  { name: "sofa-back", depth: 66, footprint: "sofa", shapes: ["691,649 743,604 768,601 955,672 968,696 968,735 896,797 691,713"] },
  { name: "lounge-lamp-table", depth: 72, footprint: "lounge-lamp-table", shapes: ["645,537 699,537 700,594 707,707 688,717 664,741 630,741 614,686 611,625 636,594 645,590"] },
  { name: "lounge-side-table", depth: 81, footprint: "lounge-side-table", shapes: ["929,717 968,701 1006,712 1014,748 1006,804 975,825 945,814 929,778"] },
  { name: "sofa-arms", depth: 74, footprint: "sofa", shapes: ["693,649 714,642 715,678 698,691 693,689", "923,710 963,695 963,746 935,779 920,770"] },
  { name: "coffee-table", depth: 78, footprint: "coffee-table", shapes: [
    "676,734 689,716 719,708 759,713 793,731 805,748 800,765 777,779 742,782 703,769 681,753",
    "680,756 692,761 686,790 676,787", "789,768 799,766 802,791 793,792",
  ] },
  // The ottoman stands on the rug in front of the coffee table; walkers pass between the two.
  { name: "ottoman", depth: 85, footprint: "ottoman", shapes: [
    "750,820 754,810 762,804 776,800 798,800 812,804 820,810 825,820 825,858 820,866 810,873 792,876 774,876 762,871 754,864 750,858",
  ] },
  { name: "lounge-chair", depth: 84, footprint: "lounge-chair", shapes: ["848,809 872,816 884,828 884,848 912,857 920,849 924,827 939,797 952,788 950,821 935,858 917,873 884,861 854,843"] },
  { name: "bed-blanket", depth: 76, footprint: "bed", shapes: ["1274,669 1339,640 1426,683 1426,733 1353,767 1269,716"] },
];

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
  return { left: Math.min(...pixels.map(([x]) => x)) / 15.36, right: Math.max(...pixels.map(([x]) => x)) / 15.36,
    top: Math.min(...pixels.map(([,y]) => y)) / 10.24, bottom: Math.max(...pixels.map(([,y]) => y)) / 10.24,
    from: Math.min(...xs), to: Math.max(...xs) };
});
// A walking sprite is SEATED_WIDTH (5%) wide and about 10% of the artwork tall above its feet.
const SPRITE = [2.5, 10.1];

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
    layer.setAttribute("viewBox", "0 0 1536 1024");
    layer.setAttribute("class", "furniture-front");
    layer.setAttribute("aria-hidden", "true");
    layer.dataset.furniture = name;
    layer.style.zIndex = depth;
    layer.innerHTML = '<defs><clipPath id="' + id + '">'
      + shapes.map((points) => '<polygon points="' + points + '"/>').join("")
      + '</clipPath></defs><image href="office.png" width="1536" height="1024" clip-path="url(#' + id + ')"/>';
    world.append(layer);
  }
  const outline = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  outline.setAttribute("viewBox","0 0 1536 1024");
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
      clone.setAttribute("x",(bounds.x-floor.x)*1536/floor.width);
      clone.setAttribute("y",(bounds.y-floor.y)*1024/floor.height);
      clone.setAttribute("width",bounds.width*1536/floor.width);
      clone.setAttribute("height",bounds.height*1024/floor.height);
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
