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

function clone(source) {
  const node = source.cloneNode(true), ids = new Map(), suffix = "-seat-copy-" + (++sequence);
  for (const item of node.querySelectorAll("[id]")) { ids.set(item.id, item.id + suffix); item.id += suffix; }
  for (const item of [node, ...node.querySelectorAll("*")]) for (const attribute of [...item.attributes])
    for (const [from, to] of ids) if (attribute.value.includes("url(#" + from + ")"))
      item.setAttribute(attribute.name, attribute.value.replaceAll("url(#" + from + ")", "url(#" + to + ")"));
  return node;
}

function viewport(data, frame, width, height, x = 0, y = 0) {
  const [left, top, w, h] = frame.box;
  const root = element("svg", { x, y, width, height, viewBox: [left, top, w, h].join(" ") });
  root.style.overflow = "hidden";
  root.append(element("image", { href: data.file, width: data.dimensions[0], height: data.dimensions[1] }));
  return root;
}

// Working hands use the seated torso's original coordinate system before the lower legs are calibrated.
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
  return { source, width: 32, height, hip, pixels,
    foot: [offset[0] + frame.sole[0] * scale, offset[1] + frame.sole[1] * scale],
    knee: offset[1] + h * (rear ? .57 : .48) * scale, ankle: offset[1] + h * (rear ? .70 : .63) * scale };
}

// Head, torso, shoes and props retain their proportions; only the calf band reaches the measured support.
// scale draws the whole seated figure smaller around the same hip, as for a Contractor (CONTRACTOR_WIDTH).
export function seatedCharacter(native, seat, scale = 1) {
  const rear = rearFacing(seat.facing), look = Number(native.dataset.look) % 6;
  let body;
  if (seat.kind === "high") {
    const row = seat.facing.startsWith("side") ? 2 : rear ? 1 : 0;
    const frame = POSES.high.frames.find((item) => item.row === row && item.column === look);
    const [, , width, height] = frame.box, hip = height * HIGH_HIPS[row], foot = frame.sole;
    const source = viewport(POSES.high, frame, width, height);
    body = { source, width, height, hip, pixels: HIGH_WIDTH / width, foot,
      knee: hip + (foot[1] - height * .1 - hip) * .2, ankle: foot[1] - height * .1 };
  } else {
    const frame = POSES.lower.frames.find((item) => item.row === (rear ? 1 : 0) && item.column === look);
    body = lowerBody(native, frame, rear);
  }
  const { source, width, height, hip, foot, knee, ankle } = body, pixels = body.pixels * scale;
  // Seen from behind, a chair sitter's feet rest forward under the table, above the measured floor point beneath
  // the hip; the rear lower part keeps its drawn length there. Front-facing feet and stool feet reach their support.
  const delta = rear && seat.kind !== "high" ? 0 : (seat.supportY - pointPixels(seat.position)[1]) / pixels - (foot[1] - hip);
  const stretch = (ankle - knee + delta) / (ankle - knee);
  if (stretch <= 0) throw new Error("Invalid seat support: " + seat.id);
  const outputHeight = height + Math.max(0, delta), root = element("svg", {
    viewBox: `0 0 ${width} ${outputHeight}`, class: "character calibrated-character", "aria-hidden": "true" });
  root.classList.add(...native.classList);
  Object.assign(root.dataset, native.dataset);
  root.style.cssText = native.style.cssText;
  const definitions = element("defs");
  const bands = [[-100, -100, width + 200, knee + 100], [-100, knee, width + 200, ankle - knee + .05],
    [-100, ankle, width + 200, height - ankle + 100]];
  native.classList.remove("character"); native.classList.add("employee-sprite");
  bands.forEach((box, index) => {
    const clip = element("clipPath", { id: "seat-band-" + (++sequence) });
    clip.append(element("rect", Object.fromEntries(["x", "y", "width", "height"].map((key, i) => [key, box[i]]))));
    definitions.append(clip);
    const drawing = index === 0 ? source : clone(source);
    // Lower bands contain atlas legs only, without invisible copies of the working hands or head.
    if (index) drawing.querySelectorAll('[data-seat-part="torso"]').forEach((node) => node.remove());
    drawing.setAttribute("width", width); drawing.setAttribute("height", height);
    const band = element("g", { "clip-path": "url(#" + clip.id + ")" }); band.append(drawing);
    const transform = index === 1 ? `translate(0 ${knee}) scale(1 ${stretch}) translate(0 ${-knee})`
      : index === 2 ? `translate(0 ${delta})` : "";
    const wrapper = element("g", { transform, "data-body-band": ["upper", "calf", "shoes"][index] });
    wrapper.append(band); root.append(wrapper);
  });
  root.prepend(definitions);
  if (seat.kind === "high") {
    const marks = element("g", { transform: `scale(${width / 32})` });
    native.querySelectorAll(".state-symbol, .state-clock").forEach((node) => marks.append(node.cloneNode(true)));
    root.append(marks);
  }
  root.dataset.seatWidth = String(width * pixels / ARTWORK.width * 100);
  root.dataset.seatRatio = width + " / " + outputHeight;
  root.dataset.seatTranslate = String(-hip / outputHeight * 100);
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
