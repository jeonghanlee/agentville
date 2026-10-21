// Furniture and actors share floor depth; foreground pixels match the room exactly.
const SURFACES = [
  { name: "studio-desks", depth: 35, shapes: [
    "286,297 294,285 367,254 367,231 383,232 427,250 427,242 474,259 474,277 604,318 604,279 654,293 654,311 697,326 697,349 731,357 729,398 686,425 685,478 627,494 443,428 444,373 306,332 306,370 288,365",
  ] },
  { name: "studio-chair-left", depth: 40, shapes: ["344,319 383,331 394,345 399,368 390,386 355,374 346,358"] },
  { name: "studio-chair-right", depth: 46, shapes: ["488,370 531,384 545,399 547,423 535,437 504,424 494,408"] },
  { name: "common-chair-left", depth: 64, shapes: ["163,565 200,579 214,594 216,620 202,635 173,618 166,602"] },
  { name: "common-chair-right", depth: 69, shapes: ["292,615 327,628 340,642 343,668 329,681 299,665 294,649"] },
  { name: "garden-chair-left", depth: 43, shapes: ["1102,344 1145,357 1158,370 1167,397 1150,414 1121,399 1107,379"] },
  { name: "garden-chair-right", depth: 49, shapes: ["1243,400 1279,413 1292,429 1296,451 1280,469 1250,454 1246,433"] },
  { name: "sofa-arms", depth: 74, shapes: ["693,649 714,642 715,678 698,691 693,689", "923,710 963,695 963,746 935,779 920,770"] },
  { name: "coffee-table", depth: 78, shapes: [
    "676,734 689,716 719,708 759,713 793,731 805,748 800,765 777,779 742,782 703,769 681,753",
    "680,756 692,761 686,790 676,787", "789,768 799,766 802,791 793,792",
  ] },
  { name: "lounge-chair", depth: 84, shapes: ["848,809 872,816 884,828 884,848 912,857 920,849 924,827 939,797 952,788 950,821 935,858 917,873 884,861 854,843"] },
  { name: "bed-blanket", depth: 76, shapes: ["1274,669 1339,640 1426,683 1426,733 1353,767 1269,716"] },
];

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
      const selected = world.querySelector(".agent.selected:not(.filtered)");
      if (!selected) { outline.replaceChildren(); previous = ""; return; }
      const bounds = selected.getBoundingClientRect(), floor = world.getBoundingClientRect();
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
      clone.querySelectorAll(".state-symbol, .state-clock").forEach((node) => node.remove());
      clone.setAttribute("class","outline-character");
      clone.setAttribute("x",(bounds.x-floor.x)*1536/floor.width);
      clone.setAttribute("y",(bounds.y-floor.y)*1024/floor.height);
      clone.setAttribute("width",bounds.width*1536/floor.width);
      clone.setAttribute("height",bounds.height*1024/floor.height);
      clone.style.removeProperty("transform");
      if (selected.dataset.seatFacing === "back-left" || selected.dataset.coffeeFacing === "left") {
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
