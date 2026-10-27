import { POSES } from "./seated-poses.js";
import { ARTWORK, ACTOR_VIEW, actorPixels, pointPixels } from "./layout.js";
import { rearFacing, mirroredFacing } from "./seats.js";

const NS = "http://www.w3.org/2000/svg";
const LOWER_WIDTH = 30, HIGH_WIDTH = 38;
const HIPS = { front: .76, back: .85 };
const HIGH_HIPS = [.69, .69, .65];
let sequence = 0;

function element(name, attributes = {}) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

function viewport(data, frame, width, height, x = 0, y = 0) {
  const [left, top, w, h] = frame.box;
  const root = element("svg", { x, y, width, height, viewBox: [left, top, w, h].join(" ") });
  root.style.overflow = "hidden";
  root.append(element("image", { href: data.file, width: data.dimensions[0], height: data.dimensions[1] }));
  return root;
}

// Working hands use the seated torso's original coordinate system.
export function seatedWorkstation(seat) {
  if (!seat?.workstation) return null;
  const rear = rearFacing(seat.facing), hip = HIPS[rear ? "back" : "front"];
  const shift = ACTOR_VIEW.height * (hip - (rear ? ACTOR_VIEW.back : ACTOR_VIEW.front)) * actorPixels() / ACTOR_VIEW.width;
  return { seat: [seat.position[0], seat.position[1] - shift / ARTWORK.height * 100, seat.facing], keys: seat.workstation };
}

function lowerBody(native, frame, rear) {
  const pixels = actorPixels() / ACTOR_VIEW.width, [, , w, h] = frame.box;
  const scale = LOWER_WIDTH / w / pixels, hip = ACTOR_VIEW.height * HIPS[rear ? "back" : "front"];
  const offset = [16 - w * (rear ? .40 : .60) * scale, hip - h * (rear ? .48 : .38) * scale];
  const waist = offset[1] + h * (rear ? .20 : .17) * scale;
  const height = Math.max(ACTOR_VIEW.height, offset[1] + h * scale);
  const source = element("svg", { viewBox: `0 0 32 ${height}` }), defs = element("defs");
  const upper = element("clipPath", { id: "seat-upper-" + (++sequence) });
  upper.append(element("rect", { x: -100, y: -100, width: 232, height: waist + 100 }));
  const lower = element("clipPath", { id: "seat-lower-" + (++sequence) });
  lower.append(element("rect", { x: -100, y: waist - .3, width: 232, height: height + 100 }));
  defs.append(upper, lower);
  const torso = element("g", { "clip-path": "url(#" + upper.id + ")", "data-seat-part": "torso" });
  native.setAttribute("width", 32); native.setAttribute("height", ACTOR_VIEW.height); torso.append(native);
  const legs = element("g", { "clip-path": "url(#" + lower.id + ")" });
  legs.append(viewport(POSES.lower, frame, w * scale, h * scale, ...offset));
  source.append(defs, torso, legs);
  return { source, width: 32, height, hip, pixels };
}

// Complete painted figures keep their proportions around the registered hip.
// A seat's floor or footrest annotation must not change a person's limb lengths.
export function seatedCharacter(native, seat, scale = 1) {
  const rear = rearFacing(seat.facing), look = Number(native.dataset.look) % 6;
  let body;
  if (seat.kind === "high") {
    const row = seat.facing.startsWith("side") ? 2 : rear ? 1 : 0;
    const frame = POSES.high.frames.find((item) => item.row === row && item.column === look);
    const [, , width, height] = frame.box, hip = height * HIGH_HIPS[row];
    const source = viewport(POSES.high, frame, width, height);
    body = { source, width, height, hip, pixels: HIGH_WIDTH / width };
  } else {
    const frame = POSES.lower.frames.find((item) => item.row === (rear ? 1 : 0) && item.column === look);
    body = lowerBody(native, frame, rear);
  }
  const { source, width, height, hip } = body, pixels = body.pixels * scale;
  const root = element("svg", {
    viewBox: `0 0 ${width} ${height}`, class: "character calibrated-character", "aria-hidden": "true" });
  root.classList.add(...native.classList);
  Object.assign(root.dataset, native.dataset);
  root.style.cssText = native.style.cssText;
  native.classList.remove("character"); native.classList.add("employee-sprite");
  source.setAttribute("width", width); source.setAttribute("height", height);
  root.append(source);
  if (seat.kind === "high") {
    const marks = element("g", { transform: `scale(${width / 32})` });
    native.querySelectorAll(".state-symbol, .state-clock").forEach((node) => marks.append(node.cloneNode(true)));
    root.append(marks);
  }
  root.dataset.seatWidth = String(width * pixels / ARTWORK.width * 100);
  root.dataset.seatRatio = width + " / " + height;
  root.dataset.seatTranslate = String(-hip / height * 100);
  root.dataset.figureScale = String(scale);
  return root;
}

export function applySeatedMetrics(node, seat) {
  const sprite = node.querySelector(":scope > .calibrated-character");
  node.style.aspectRatio = sprite?.dataset.seatRatio || "";
  node.style.transform = sprite ? `translate(-50%,${sprite.dataset.seatTranslate}%)` : "";
  node.style.clipPath = "";
  if (!sprite) return;
  node.style.width = sprite.dataset.seatWidth + "%";
  if (seat.edge) {
    const [width, height] = sprite.getAttribute("viewBox").split(/\s+/).map(Number).slice(2);
    const pxWidth = Number(sprite.dataset.seatWidth) / 100 * ARTWORK.width;
    const pxHeight = height / width * pxWidth, hip = -Number(sprite.dataset.seatTranslate) / 100 * pxHeight;
    const position = pointPixels(seat.position), origin = [position[0] - pxWidth / 2, position[1] - hip];
    const [[x0, y0], [x1, y1]] = seat.edge, slope = (y1 - y0) / (x1 - x0);
    const edge = (x) => (y0 + (x - x0) * slope - origin[1]) / pxHeight * 100;
    node.style.clipPath = `polygon(-500% -500%,600% -500%,600% ${edge(origin[0] + pxWidth * 6)}%,-500% ${edge(origin[0] - pxWidth * 5)}%)`;
  }
  if (mirroredFacing(seat.facing) || seat.facing === "side-left") sprite.style.transform = "scaleX(-1)";
}
