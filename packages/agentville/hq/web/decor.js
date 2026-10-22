// Code-drawn decoration over office.png: paintings inside the existing wall frames and a few flower props.
// Choices follow the Branch id, so each Branch looks distinct but stable. No text, logos, or Branch data is drawn.
const NS = "http://www.w3.org/2000/svg";
const CELL = 4;
// Inner edge of each wall frame in office.png pixels: top-left, top-right, bottom-right, bottom-left.
const FRAMES = [
  { name: "studio-left", quad: [[286,152],[339,127],[339,211],[286,236]] },
  { name: "studio-back", quad: [[780,166],[850,190],[850,262],[780,238]] },
  // A plant stands in front of this frame; its leaves are redrawn from office.png above the painting.
  { name: "common", quad: [[80,485],[124,464],[124,523],[80,544]],
    front: "60,522 66,519 72,521 80,524 86,521 93,522 100,526 106,531 110,538 113,548 116,560 60,560" },
  // The lounge wall is redrawn above walkers in the aisle behind it, so its painting sits just above that layer.
  { name: "lounge", quad: [[749,468],[799,444],[799,516],[749,540]], depth: 59 },
  { name: "studio-right", quad: [[1247,226],[1313,252],[1313,326],[1247,300]] },
];
// Free furniture surfaces in office.png pixels (vase base) and stacking depth; none is a seat or a floor route.
const FLOWER_SPOTS = [
  { name: "coffee-table", at: [792,757], depth: 79 },
  { name: "fridge-top", at: [940,583], depth: 60 },
  { name: "studio-cabinet", at: [777,276], depth: 33 },
  { name: "window-sill", at: [1394,630], depth: 62 },
  { name: "common-desk", at: [140,553], depth: 60 },
];
const C = {
  cream: "#efe3c8", mat: "#f3ead8", sand: "#e2c9a0", peach: "#eab48a", terracotta: "#c58261", rust: "#a8613f",
  sage: "#a4b792", olive: "#7f9570", moss: "#5f7a4f", sky: "#a9c4c9", mist: "#d4e0dc", lavender: "#b8a4c8",
  plum: "#8d6f8f", mustard: "#d9b45a", navy: "#5b6f86", brown: "#7a5a3f", rose: "#d08a86", night: "#3e4a63", white: "#f8f2e4",
};

function seeded(text) {
  let state = Array.from(String(text)).reduce((hash, ch) => Math.imul(hash ^ ch.charCodeAt(0), 16777619) >>> 0, 2166136261);
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Paintings fill a cols x rows grid; each returns a colour (or null for the background) per cell.
const PAINTINGS = {
  hills(cols, rows, r) {
    const sun = [2 + Math.floor(r() * (cols - 4)), 2 + Math.floor(r() * 2)];
    const far = Array.from({ length: cols }, (_, x) => Math.round(rows * .5 + Math.sin(x / 2.2 + r()) * 1.2));
    const near = Array.from({ length: cols }, (_, x) => Math.round(rows * .68 + Math.sin(x / 3 + 2) * 1.5));
    return (x, y) => y >= near[x] ? (y > rows * .85 ? C.moss : C.olive) : y >= far[x] ? C.sage
      : Math.hypot(x - sun[0], y - sun[1]) < 1.6 ? C.mustard : y < rows * .22 ? C.peach : C.sand;
  },
  sea(cols, rows, r) {
    const horizon = Math.round(rows * (.42 + r() * .12)), boat = 1 + Math.floor(r() * (cols - 4));
    return (x, y) => {
      if (y === horizon - 1 && x >= boat && x < boat + 3) return C.brown;
      if (x === boat + 1 && y >= horizon - 4 && y < horizon - 1) return C.white;
      if (y < horizon) return y < horizon / 2 ? C.sky : C.mist;
      return (x + y) % 5 === 0 ? C.mist : y > rows * .8 ? C.navy : "#7f9cab";
    };
  },
  botanical(cols, rows, r) {
    const stem = Math.floor(cols / 2), bloom = r() < .5 ? C.rose : C.mustard;
    return (x, y) => {
      if (y < 4 && Math.abs(x - stem) + Math.abs(y - 2) <= 1) return bloom;
      if (x === stem && y >= 3 && y < rows - 1) return C.moss;
      const leaf = (y - 4) % 3;
      if (y > 3 && y < rows - 2 && leaf === 0 && (x === stem - 1 - (y % 2) || x === stem + 1 + ((y + 1) % 2))) return C.olive;
      return y >= rows - 1 ? C.sand : C.cream;
    };
  },
  blocks(cols, rows, r) {
    const a = 2 + Math.floor(r() * (cols - 4)), b = 2 + Math.floor(r() * (rows - 4));
    const colours = [C.terracotta, C.sage, C.mustard, C.lavender, C.sky, C.peach].sort(() => r() - .5);
    return (x, y) => x === a || y === b ? C.cream : colours[(x > a ? 1 : 0) + (y > b ? 2 : 0)];
  },
  circles(cols, rows, r) {
    const centre = [cols / 2 - .5 + (r() - .5) * 2, rows / 2 - .5 + (r() - .5) * 2];
    const rings = [C.rust, C.peach, C.mustard, C.cream];
    return (x, y) => {
      const d = Math.hypot(x - centre[0], (y - centre[1]) * .9);
      return d < 6.5 ? rings[Math.floor(d / 1.7) % rings.length] : C.sage;
    };
  },
  mountains(cols, rows, r) {
    const peaks = [Math.floor(cols * .3), Math.floor(cols * .72)].map((x) => [x + Math.floor(r() * 2), Math.round(rows * (.25 + r() * .15))]);
    return (x, y) => {
      for (const [px, py] of peaks) {
        if (y >= py && Math.abs(x - px) <= y - py) return y - py < 2 ? C.white : y > rows * .75 ? C.olive : C.navy;
      }
      return y > rows * .82 ? C.olive : y < rows * .3 ? C.mist : C.sky;
    };
  },
  arches(cols, rows) {
    const bands = [C.rust, C.terracotta, C.peach, C.mustard, C.sage, C.sky];
    const reach = Math.max(cols / 2, rows * .8);
    return (x, y) => {
      const d = Math.hypot(x - cols / 2 + .5, y - rows + 1);
      const band = Math.floor((reach - d) / (reach / (bands.length + 1)));
      return band >= 0 && band < bands.length ? bands[band] : y < 2 ? C.peach : C.cream;
    };
  },
  vase(cols, rows, r) {
    const mid = Math.floor(cols / 2), bloom = [C.rose, C.lavender, C.mustard][Math.floor(r() * 3)];
    return (x, y) => {
      if (y >= rows - 5 && y < rows - 1 && Math.abs(x - mid) <= (y === rows - 5 ? 1 : 2)) return C.terracotta;
      if (y >= rows - 1) return C.brown;
      if (y >= 4 && y < rows - 5 && (x === mid || (y > 6 && Math.abs(x - mid) === 1 && y % 2))) return C.moss;
      if (y >= 2 && y < 5 && (x - mid) ** 2 + (y - 3) ** 2 <= 4) return (x + y) % 2 ? bloom : C.white;
      return C.mist;
    };
  },
  tree(cols, rows, r) {
    const trunk = Math.floor(cols / 2) + (r() < .5 ? 0 : 1), ground = rows - 3;
    return (x, y) => {
      if (y >= ground) return y === ground ? C.olive : C.moss;
      if (x === trunk && y > ground - 5) return C.brown;
      if (Math.hypot(x - trunk, (y - ground + 8) * 1.1) < 3.4) return (x * 3 + y) % 4 ? C.olive : C.sage;
      return y < 3 ? C.peach : C.cream;
    };
  },
  night(cols, rows, r) {
    const moon = [2 + Math.floor(r() * (cols - 5)), 3];
    const stars = new Set(Array.from({ length: 6 }, () => Math.floor(r() * cols) + "," + Math.floor(r() * rows * .6)));
    return (x, y) => {
      if (y > rows * .78) return C.moss;
      const d = Math.hypot(x - moon[0], y - moon[1]);
      if (d < 2.3 && Math.hypot(x - moon[0] - 1.2, y - moon[1] + .4) > 1.9) return C.mustard;
      if (stars.has(x + "," + y)) return C.white;
      return y < rows * .4 ? C.night : C.navy;
    };
  },
};
const NAMES = Object.keys(PAINTINGS);

// Slight per-cell tone changes read as brush strokes in the pixel style.
function tone(hex, shift) {
  const n = parseInt(hex.slice(1), 16);
  const ch = (v) => Math.max(0, Math.min(255, Math.round(v * (1 + shift))));
  return "#" + [ch(n >> 16), ch((n >> 8) & 255), ch(n & 255)].map((v) => v.toString(16).padStart(2, "0")).join("");
}

function painting(frame, name, random, id) {
  const [tl, tr, , bl] = frame.quad;
  const width = Math.hypot(tr[0] - tl[0], tr[1] - tl[1]), height = bl[1] - tl[1];
  const cols = Math.max(8, Math.round(width / CELL)), rows = Math.max(10, Math.round(height / CELL));
  const inner = [cols - 2, rows - 2];
  const paint = PAINTINGS[name](inner[0], inner[1], random);
  let cells = "";
  for (let y = 0; y < inner[1]; y++) {
    for (let x = 0; x < inner[0]; x++) {
      const colour = paint(x, y) || C.cream;
      cells += '<rect x="' + (x + 1) + '" y="' + (y + 1) + '" width="1.04" height="1.04" fill="' + tone(colour, (random() - .5) * .08) + '"/>';
    }
  }
  const matrix = [(tr[0] - tl[0]) / cols, (tr[1] - tl[1]) / cols, (bl[0] - tl[0]) / rows, (bl[1] - tl[1]) / rows, tl[0], tl[1]];
  return '<clipPath id="' + id + '"><polygon points="' + frame.quad.map((p) => p.join(",")).join(" ") + '"/></clipPath>'
    + '<g clip-path="url(#' + id + ')"><g transform="matrix(' + matrix.map((v) => v.toFixed(4)).join(" ") + ')" shape-rendering="crispEdges">'
    + '<rect width="' + cols + '" height="' + rows + '" fill="' + C.mat + '"/>' + cells
    + '<path d="M1 1h' + inner[0] + 'v.35H1.35V' + (inner[1] + 1) + 'H1Z" fill="#5f5440" opacity=".18"/></g></g>';
}

// Flowers: a vase or pot with blossoms, drawn on a 2 px grid at the office scale.
const VASES = [
  { kind: "tulips", body: "M-4 0h8v-2h1v-6h-1v-2h-2v-2h-4v2h-2v2h-1v6h1Z" },
  { kind: "pot", body: "M-5 0h10v-1h1v-5h-12v5h1Z" },
  { kind: "jar", body: "M-3 0h6v-1h1v-7h-1v-1h-6v1h-1v7h1Z" },
  { kind: "bowl", body: "M-4 0h8v-1h2v-2h1v-2h-14v2h1v2h2Z" },
];
// Flower art units are office pixels at this scale, close to the size of the mugs and plants in the artwork.
const FLOWER_SCALE = 1.7;
const BLOOMS = [["#e58c8a", "#f6c3b5"], ["#f2c94c", "#fff0b3"], ["#f8f2e4", "#f2c94c"], ["#c36a9c", "#eab0d2"], ["#9f8ccf", "#d9cdf0"], ["#e07a4f", "#f5b98e"]];
const VASE_COLOURS = [["#c58261", "#8f5c45"], ["#8995ad", "#66718a"], ["#e5d5b6", "#b9a482"], ["#a4b792", "#6b845c"], ["#d4a1a1", "#a57678"]];

function flower(spot, random) {
  const vase = VASES[Math.floor(random() * VASES.length)];
  const [glaze, shade] = VASE_COLOURS[Math.floor(random() * VASE_COLOURS.length)];
  const blooms = BLOOMS.slice().sort(() => random() - .5).slice(0, 2);
  const top = { tulips: -12, pot: -6, jar: -9, bowl: -5 }[vase.kind];
  const stems = vase.kind === "pot" ? 4 : 3;
  let art = '<ellipse cx="0" cy=".5" rx="6" ry="1.4" fill="#4a3b2a" opacity=".18"/>';
  for (let i = 0; i < stems; i++) {
    const x = Math.round((i - (stems - 1) / 2) * (vase.kind === "pot" ? 3 : 3.4) + (random() - .5) * 2);
    const height = 7 + Math.floor(random() * 6);
    const y = top - height;
    const [petal, centre] = blooms[i % blooms.length];
    art += '<path d="M' + x + ' ' + top + 'V' + (y + 2) + '" stroke="#5f7a4f" stroke-width="1.2"/>'
      + (i % 2 ? '<path d="M' + x + ' ' + (top - 3) + 'h-2v-1h1v-1h1Z" fill="#7f9570"/>' : '<path d="M' + x + ' ' + (top - 4) + 'h2v-1h-1v-1h-1Z" fill="#7f9570"/>');
    art += vase.kind === "tulips"
      ? '<path d="M' + (x - 2) + ' ' + (y + 2) + 'v-3h1v1h1v-2h1v1h1v-1h1v4h-1v1h-3Z" fill="' + petal + '"/><path d="M' + x + ' ' + (y - 1) + 'h1v2h-1Z" fill="' + centre + '"/>'
      : '<path d="M' + (x - 1) + ' ' + (y - 2) + 'h2v1h1v2h-1v1h-2v-1h-1v-2h1Z" fill="' + petal + '"/><path d="M' + x + ' ' + (y - 1) + 'h1v1h-1Z" fill="' + centre + '"/>';
  }
  art += '<path d="' + vase.body + '" fill="' + glaze + '" stroke="' + shade + '" stroke-width=".8"/>'
    + '<path d="M-2 ' + (top + 2) + 'v' + (-top - 4) + '" stroke="#ffffff" stroke-opacity=".35" stroke-width="1"/>';
  return '<g class="flower" data-spot="' + spot.name + '" data-vase="' + vase.kind + '" transform="translate(' + spot.at.join(" ") + ') scale(' + FLOWER_SCALE + ')" shape-rendering="crispEdges">' + art + '</g>';
}

export function mountDecor(world) {
  const walls = FRAMES.map((frame) => {
    const layer = document.createElementNS(NS, "svg");
    layer.setAttribute("viewBox", "0 0 1536 1024");
    layer.setAttribute("class", "wall-art");
    layer.setAttribute("aria-hidden", "true");
    layer.style.zIndex = String(frame.depth || 1);
    world.append(layer);
    return { frame, layer };
  });
  const flowers = FLOWER_SPOTS.map((spot) => {
    const layer = document.createElementNS(NS, "svg");
    layer.setAttribute("viewBox", "0 0 1536 1024");
    layer.setAttribute("class", "flower-layer");
    layer.setAttribute("aria-hidden", "true");
    layer.style.zIndex = String(spot.depth);
    world.append(layer);
    return { spot, layer };
  });
  let shown = null;
  return {
    update(branch) {
      const key = String(branch || "office");
      if (key === shown) return;
      shown = key;
      const random = seeded("decor:" + key);
      // A Branch-specific order of paintings, so frames in one office never repeat a painting.
      const order = NAMES.slice().sort(() => random() - .5);
      walls.forEach(({ frame, layer }, i) => {
        const id = "wall-art-" + i;
        layer.innerHTML = '<g class="painting" data-frame="' + frame.name + '" data-painting="' + order[i] + '">'
          + painting(frame, order[i], seeded("painting:" + key + ":" + i), id)
          + (frame.front ? '<clipPath id="' + id + '-front"><polygon points="' + frame.front + '"/></clipPath>'
            + '<image href="office.png" width="1536" height="1024" clip-path="url(#' + id + '-front)"/>' : '') + '</g>';
      });
      for (const { spot, layer } of flowers) layer.innerHTML = flower(spot, seeded("flower:" + key + ":" + spot.name));
    },
  };
}
