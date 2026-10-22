import { mugArtwork, randomMug } from "./mugs.js";

const NS = "http://www.w3.org/2000/svg";
export const SEATED_WIDTH = 5;
const PEOPLE_SIZE = [1536, 1024];
const CATS_SIZE = [1024, 1536];
const SLEEPING = [[40,60,485,414],[575,88,450,379],[1047,59,464,417],[23,556,506,407],[557,575,473,395],[1043,557,470,412]];
const COFFEE_STANDING = [[273,18,212,480],[649,40,215,455],[1027,24,216,475],[272,514,221,468],[674,519,192,466],[1045,514,210,476]];
const CAT_SCALE = 34 / 385;
const PEOPLE = [
  [[78,38,143,335], [65,386,161,300], [75,690,184,282]],
  [[331,47,145,324], [323,400,147,284], [332,712,177,253]],
  [[576,38,146,333], [557,392,160,294], [580,707,176,262]],
  [[818,25,148,347], [802,383,158,304], [836,703,178,266]],
  [[1072,38,152,335], [1058,392,165,298], [1083,698,178,271]],
  [[1316,38,144,335], [1307,389,166,301], [1325,693,181,281]],
];
const HEAD_END = [[183,526,815], [191,534,827], [194,539,822], [192,534,827], [190,534,821], [192,540,824]];
const HANDS = [
  [[[80,211,35,46],[172,214,45,44]], [[71,536,38,34],[111,542,47,35]], [[186,824,31,27],[216,825,35,39]]],
  [[[335,202,47,47],[408,217,43,43]], [[321,540,44,35],[363,547,48,37]], [[439,823,32,30],[469,832,34,38]]],
  [[[586,199,42,47],[619,209,45,45]], [[560,539,40,36],[600,549,48,37]], [[683,823,31,32],[715,832,36,38]]],
  [[[825,207,48,47],[867,215,46,45]], [[802,538,45,36],[847,547,50,39]], [[933,824,35,33],[963,832,39,40]]],
  [[[1075,208,38,44],[1132,190,48,51]], [[1061,539,48,35],[1107,550,50,39]], [[1183,825,33,32],[1213,832,40,40]]],
  [[[1320,196,43,50],[1407,221,43,44]], [[1311,535,46,35],[1358,545,51,39]], [[1430,824,33,32],[1458,828,40,42]]],
];
const CAT_FRAMES = {
  ginger: [[160,38,327,379], [170,451,289,348], [143,822,310,336], [146,1219,333,241]],
  tuxedo: [[610,42,333,385], [601,454,293,348], [614,827,295,347], [602,1225,330,238]],
};
const CAT_WALK_PARTS = {
  ginger: [[161,38,94,145],[163,259,63,61],[249,299,52,43],[312,332,100,87]],
  tuxedo: [[610,42,79,143],[622,261,59,57],[707,301,49,46],[783,342,88,86]],
};
let sequence = 0;

function viewport(file, frame, dimensions, width, height, scale = null) {
  const [x,y,w,h] = frame;
  const factor = scale ?? Math.min(width / w, height / h);
  return '<svg x="' + ((width - w * factor) / 2) + '" y="' + (height - h * factor)
    + '" width="' + (w * factor) + '" height="' + (h * factor) + '" viewBox="' + frame.join(" ")
    + '"><image href="' + file + '" width="' + dimensions[0] + '" height="' + dimensions[1] + '"/></svg>';
}

function rect([x,y,w,h], fill = "") {
  return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '"' + (fill ? ' fill="' + fill + '"' : "") + '/>';
}

function localRect(frame, region) {
  const [x,y,w,h] = frame, [rx,ry,rw,rh] = region;
  const scale = Math.min(32 / w, 43 / h);
  return [(32-w*scale)/2+(rx-x)*scale, 43-h*scale+(ry-y)*scale, rw*scale, rh*scale];
}

export function employeeSprite(look, state, detail, condition, contractor, desk, workstation, cup = randomMug()) {
  if (desk === "lying") return sleepingSprite(look, state);
  if (desk === "coffee-back") return coffeeSprite(look,state,detail,cup);
  const pose = desk.startsWith("back") ? 2 : desk === "front" ? 1 : 0;
  const frame = PEOPLE[look.style][pose];
  const head = localRect(frame, [frame[0],frame[1],frame[2],HEAD_END[look.style][pose]-frame[1]]);
  const [left,right] = HANDS[look.style][pose].map((region) => localRect(frame, region));
  const id = "employee-parts-" + (++sequence);
  const art = viewport("employees" + (look.suffix || "") + ".png", frame, PEOPLE_SIZE, 32, 43);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 32 43");
  svg.setAttribute("class", "character textured-character");
  svg.setAttribute("aria-hidden", "true");
  svg.dataset.activity = state;
  if (desk) svg.dataset.pose = desk;
  svg.style.setProperty("--left-pivot", (left[0]+left[2]/2) + "px " + left[1] + "px");
  svg.style.setProperty("--right-pivot", (right[0]+right[2]/2) + "px " + right[1] + "px");
  svg.innerHTML = '<defs><mask id="' + id + '-body" maskUnits="userSpaceOnUse" x="0" y="0" width="32" height="43">'
    + rect([0,0,32,43],"white") + rect(head,"black") + rect(left,"black") + rect(right,"black")
    + '</mask><clipPath id="' + id + '-head">' + rect(head) + '</clipPath><clipPath id="' + id + '-left">'
    + rect(left) + '</clipPath><clipPath id="' + id + '-right">' + rect(right) + '</clipPath></defs>'
    + '<g class="body" mask="url(#' + id + '-body)">' + art + '</g><g class="head" clip-path="url(#' + id + '-head)">' + art
    + '</g><g class="hand-left" clip-path="url(#' + id + '-left)">' + art + '</g><g class="pointer-hand"><g class="hand-right" clip-path="url(#' + id + '-right)">' + art + '</g></g>';
  // Contractors wear a safety-yellow hard hat with a dark outline so they read apart from Employee hats.
  if (contractor) svg.insertAdjacentHTML("beforeend", '<g class="hard-hat" stroke="#4a3812" stroke-width=".9" stroke-linejoin="round">'
    + '<path d="M7.6 9.6C7.6 1.6 24.4 1.6 24.4 9.6Z" fill="#f6c51f"/>'
    + '<path d="M14.6 3v6.4h2.8V3" fill="#ffe27a" stroke-width=".6"/>'
    + '<rect x="5.2" y="9.1" width="21.6" height="2.3" rx="1.1" fill="#e9ab0c"/>'
    + '<path d="M10 5.6q1.5-2 4-2.4" fill="none" stroke="#fff4c4" stroke-width=".8" stroke-linecap="round"/></g>');
  const symbol = { thinking: "...", waiting: "!", unknown: "?", error: "+" }[state]
    || (detail === "dozing" ? "z" : "");
  if (symbol) {
    const mark = document.createElementNS(NS, "text");
    mark.setAttribute("class", "state-symbol"); mark.setAttribute("x", "27"); mark.setAttribute("y", "5");
    mark.setAttribute("fill", "#8b795d"); mark.setAttribute("font-size", "6"); mark.textContent = symbol;
    svg.append(mark);
  }
  const hand = svg.querySelector(".hand-left");
  // Props follow the hand outside its atlas clip.
  const prop = document.createElementNS(NS, "g");
  prop.setAttribute("class", "hand-prop");
  prop.setAttribute("transform", "translate(" + (left[0]+left[2]/2-1.5) + " " + (left[1]-1) + ")");
  if (detail === "phone") prop.innerHTML = '<rect width="3.5" height="5.5" rx=".6" fill="#3b4541" stroke="#788278" stroke-width=".5"/><path d="M1 1h1.5v3H1Z" fill="#b8c8b2"/>';
  else if (condition === "extra-coffee" || detail === "fika") prop.innerHTML = mugArtwork(cup,-.7,-1);
  if (prop.childElementCount) {
    const grip = document.createElementNS(NS,"g");
    grip.setAttribute("class", "held-item");
    grip.style.setProperty("--left-pivot", svg.style.getPropertyValue("--left-pivot"));
    hand.before(grip); grip.append(hand,prop);
  }
  // Study mode keeps a small book stack on the desk side of the character.
  const books = pose === 2 ? [24,15] : pose === 1 ? [23,22] : [23,30];
  if (condition === "study-mode") svg.insertAdjacentHTML("beforeend", '<g class="study-books" transform="translate(' + books.join(" ") + ')" stroke="#5f5440" stroke-width=".3">'
    + '<rect y="4.8" width="8" height="2.2" rx=".3" fill="#7f9570"/><path d="M.7 5.5h6.6" stroke="#f1e8ce" stroke-width=".7"/>'
    + '<rect x=".8" y="2.8" width="6.4" height="2" rx=".3" fill="#b67c57"/><path d="M1.4 3.5h5.2" stroke="#f1e8ce" stroke-width=".6"/>'
    + '<rect x=".3" y=".7" width="7" height="2.1" rx=".3" fill="#8995ad" transform="rotate(-6 4 1.7)"/></g>');
  if (state === "limited") svg.insertAdjacentHTML("beforeend", '<g class="state-clock"><circle cx="27" cy="5" r="3" fill="#f2e9d0" stroke="#9e8d69" stroke-width=".7"/><path d="M27 3v2l1.5 1" fill="none" stroke="#7c745b" stroke-width=".6"/></g>');
  if (workstation && state === "working") {
    const { seat, keys } = workstation;
    const width = PEOPLE_SIZE[0] * SEATED_WIDTH / 100;
    const height = width * 43 / 32;
    const origin = [seat[0] * PEOPLE_SIZE[0] / 100 - width / 2,
      seat[1] * PEOPLE_SIZE[1] / 100 - height * (seat[2].startsWith("back") ? .78 : .64)];
    const targets = keys.map(([x,y]) => [(x-origin[0])*32/width,(y-origin[1])*43/height]);
    [left,right].forEach((region,index) => {
      const start = [region[0]+region[2]/2,region[1]+region[3]/2];
      const target = targets[index];
      const arm = document.createElementNS(NS,"path");
      arm.setAttribute("d", "M" + start.join(" ") + "Q" + start[0] + " " + target[1] + " " + target.join(" "));
      arm.setAttribute("fill","none"); arm.setAttribute("stroke",look.dark);
      arm.setAttribute("stroke-width","2.3"); arm.setAttribute("stroke-linecap","round");
      const cuff = document.createElementNS(NS,"g");
      cuff.setAttribute("clip-path","url(#" + id + (index ? "-right" : "-left") + ")");
      const cloth = pose === 2 ? [12,27] : [21,27];
      cuff.innerHTML = '<g transform="translate(' + (start[0]-cloth[0]) + ' ' + (start[1]-cloth[1]) + ')">' + art + '</g>';
      svg.querySelector(".head").before(cuff);
      svg.querySelector(".head").before(arm);
      const reach = document.createElementNS(NS,"g");
      reach.setAttribute("class", "keyboard-reach");
      reach.setAttribute("transform", "translate(" + (target[0]-start[0]) + " " + (target[1]-start[1]) + ")");
      const part = index ? svg.querySelector(".pointer-hand") : svg.querySelector(".held-item, .hand-left");
      part.before(reach); reach.append(part);
    });
    svg.style.setProperty("--mouse-x", (targets[2][0]-targets[1][0]) + "px");
    svg.style.setProperty("--mouse-y", (targets[2][1]-targets[1][1]) + "px");
    svg.append(svg.querySelector(".head"));
  }
  return svg;
}

// A switched-off monitor for limited Employees whose screen is not visible in the room artwork.
export function screenOffSprite() {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 12 11");
  svg.setAttribute("class", "screen-off");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = '<rect x=".5" y=".5" width="11" height="7.5" rx="1" fill="#353d39" stroke="#7d8578" stroke-width=".6"/>'
    + '<path d="M2 2.2l2.5-.8" stroke="#56605a" stroke-width=".6" stroke-linecap="round"/>'
    + '<path d="M5 8v1.6M3.5 10h5" stroke="#7d8578" stroke-width=".8" stroke-linecap="round"/>'
    + '<circle cx="10" cy="7" r=".45" fill="#d39a5a"/>';
  return svg;
}

function sleepingSprite(look, state) {
  const svg = document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 48 40");
  svg.setAttribute("class","character textured-character sleeping-character");
  svg.setAttribute("aria-hidden","true");
  svg.dataset.activity = state;
  svg.dataset.pose = "lying";
  svg.innerHTML = '<g class="sleeping-body">' + viewport("sleeping" + (look.suffix || "") + ".png", SLEEPING[look.style], PEOPLE_SIZE, 48, 40)
    + '</g><text class="state-symbol" x="18" y="2" fill="#8b795d" font-size="4">z</text>';
  return svg;
}

function coffeeSprite(look, state, detail, cup) {
  const svg = document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 32 43");
  svg.setAttribute("class","character textured-character coffee-character");
  svg.setAttribute("aria-hidden","true");
  svg.dataset.activity = state;
  svg.dataset.pose = "coffee-back";
  svg.innerHTML = '<g class="coffee-person">' + viewport("coffee-standing" + (look.suffix || "") + ".png",COFFEE_STANDING[look.style],PEOPLE_SIZE,32,43)
    + (detail === "coffee-cup" ? mugArtwork(cup,21,20) : '') + '</g>';
  if (detail === "coffee-wait") svg.insertAdjacentHTML("beforeend",'<g class="brewing-steam" fill="none" stroke="#f4dfb4" stroke-width=".7" stroke-linecap="round"><path d="M26 15q-2-2 0-4t0-4M29 16q-2-2 0-4"/></g>');
  return svg;
}

export function catSprite(coat) {
  const frames = CAT_FRAMES[coat] || CAT_FRAMES.ginger;
  const svg = document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 44 34");
  svg.setAttribute("class","cat-art textured-cat");
  svg.setAttribute("aria-hidden","true");
  const poses = ["cat-walking", "cat-sitting", "cat-grooming", "cat-sleeping"];
  svg.innerHTML = '<ellipse cx="22" cy="32.8" rx="13" ry="1.2" fill="#65583f" opacity=".16"/><g class="cat-facing">'
    + frames.map((frame,i) => '<g class="' + poses[i] + '"><g class="' + (i === 3 ? "cat-sleep-breath" : "cat-torso") + '">'
      + (i === 0 ? walkingCat(coat,frame) : viewport("cats.png", frame, CATS_SIZE, 44, 34, CAT_SCALE)) + '</g></g>').join("") + '</g>';
  return svg;
}

function walkingCat(coat, frame) {
  const id = "cat-walk-" + (++sequence);
  const art = viewport("cats.png",frame,CATS_SIZE,44,34,CAT_SCALE);
  const parts = (CAT_WALK_PARTS[coat] || CAT_WALK_PARTS.ginger).map(([x,y,w,h]) => [
    (44-frame[2]*CAT_SCALE)/2+(x-frame[0])*CAT_SCALE,
    34-frame[3]*CAT_SCALE+(y-frame[1])*CAT_SCALE,w*CAT_SCALE,h*CAT_SCALE]);
  const names = ["cat-tail", "cat-leg cat-leg-back", "cat-leg cat-leg-far", "cat-leg cat-leg-front"];
  return '<defs><mask id="' + id + '-body" maskUnits="userSpaceOnUse" x="0" y="0" width="44" height="34">'
    + rect([0,0,44,34],"white") + parts.map((part) => rect(part,"black")).join("") + '</mask>'
    + parts.map((part,i) => '<clipPath id="' + id + '-' + i + '">' + rect(part) + '</clipPath>').join("") + '</defs>'
    + '<g mask="url(#' + id + '-body)">' + art + '</g>'
    + parts.map((part,i) => '<g class="' + names[i] + '" style="transform-origin:' + (part[0]+part[2]/2) + 'px ' + (i === 0 ? part[1]+part[3] : part[1]) + 'px" clip-path="url(#' + id + '-' + i + ')">' + art + '</g>').join("");
}
