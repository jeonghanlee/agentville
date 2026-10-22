export const MUGS = [
  { name: "cream", color: "#e5d5b6", shade: "#b9a482", motif: "" },
  { name: "sage", color: "#a4b792", shade: "#6b845c", motif: "" },
  { name: "terracotta", color: "#c58261", shade: "#905d46", motif: "" },
  { name: "midnight", color: "#668297", shade: "#435968", motif: "" },
  { name: "stripes", color: "#e5d8b7", shade: "#ae9f7f", motif: '<path d="M2 6h6M2 8h6" stroke="#8eab9d" stroke-width="1.1"/>' },
  { name: "dots", color: "#d4a1a1", shade: "#a57678", motif: '<g fill="#f3e4cb"><circle cx="3" cy="6" r=".55"/><circle cx="6" cy="7" r=".55"/><circle cx="4" cy="9" r=".55"/></g>' },
  { name: "daisy", color: "#b5c1a2", shade: "#7c8e6c", motif: '<g fill="#f1e8ce"><circle cx="4" cy="6" r="1"/><circle cx="6" cy="6" r="1"/><circle cx="5" cy="5" r="1"/><circle cx="5" cy="7" r="1"/></g><circle cx="5" cy="6" r=".65" fill="#c7a053"/>' },
  { name: "checker", color: "#eadabe", shade: "#af9a7e", motif: '<path d="M2 5h2v2H2Zm2 2h2v2H4Zm2-2h2v2H6Z" fill="#9b8671"/>' },
  { name: "cat", color: "#dfbb7c", shade: "#af8752", motif: '<path d="M3 7V5l1.5 1h1L7 5v2q0 2-2 2T3 7Z" fill="#8b6748"/><path d="M4 7h.1M6 7h.1" stroke="#f3deaf" stroke-linecap="round"/>' },
  { name: "takeaway", color: "#dfd0ac", shade: "#b1a07d", motif: '<path d="M2 6h6v3H2Z" fill="#8b9f82"/>' },
];

export function randomMug(previous = -1) {
  const choices = MUGS.map((_,index) => index).filter((index) => index !== previous);
  return choices[Math.floor(Math.random()*choices.length)];
}

export function mugArtwork(index, x, y) {
  const mug = MUGS[index] || MUGS[0];
  return '<svg class="coffee-cup" data-cup="' + mug.name + '" x="' + x + '" y="' + y + '" width="4.8" height="5.5" viewBox="0 0 12 14">'
    + '<path d="M8 5h1q3 0 1 4H8" fill="none" stroke="' + mug.shade + '" stroke-width="1.2"/>'
    + '<path d="M1.5 3.5h7L8 10q-3 2-6 0Z" fill="' + mug.color + '" stroke="' + mug.shade + '" stroke-width=".6"/>'
    + '<path d="M7.5 4v5.5q-.5 1-2 1" fill="none" stroke="' + mug.shade + '" opacity=".5"/>'
    + '<ellipse cx="5" cy="3.5" rx="3.5" ry="1.2" fill="#ede1c5"/><ellipse cx="5" cy="3.5" rx="2.7" ry=".7" fill="#69513d"/>'
    + mug.motif + (mug.name === "takeaway" ? '<path d="M1 3h8v2H1Z" fill="#51514a"/>' : '') + '</svg>';
}

// Lounge drinks: coffee and tea use the mug designs; other drinks have their own glass, can, or cup.
export const DRINKS = ["coffee", "tea", "juice", "water", "soda", "milk"];
export const HOT_DRINKS = new Set(["coffee", "tea"]);
const GLASS = '<path d="M2.4 1.6h6.2L8 12.2q-2.5 1-5 0Z" fill="#eef4ef" fill-opacity=".55" stroke="#9fb0a6" stroke-width=".6"/>';
const GLINT = '<path d="M3.4 3v7" stroke="#ffffff" stroke-opacity=".7" stroke-width=".55"/>';

function glassArtwork(kind) {
  if (kind === "juice") return GLASS + '<path d="M2.7 4.2h5.6L8 12q-2.5.9-5 0Z" fill="#f0a238"/><path d="M2.8 4.2h5.4" stroke="#f7c66a" stroke-width=".6"/>'
    + '<path class="stir-straw" d="M6.6 6.5 8.4.2" stroke="#d6605a" stroke-width=".7" stroke-linecap="round"/>'
    + '<path d="M7.2 1.2a1.6 1.6 0 0 1 2.6 1" fill="#f6b13c" stroke="#c97d22" stroke-width=".4"/>' + GLINT;
  if (kind === "water") return GLASS + '<path d="M2.7 4.8h5.6L8 12q-2.5.9-5 0Z" fill="#b9dde6" fill-opacity=".9"/><path d="M2.8 4.8h5.4" stroke="#e3f3f6" stroke-width=".5"/>'
    + '<rect x="4.4" y="6.2" width="1.4" height="1.4" fill="#e9f7fa" stroke="#a8ccd5" stroke-width=".3" transform="rotate(12 5 7)"/>' + GLINT;
  return GLASS + '<path d="M2.6 2.8h5.8L8 12q-2.5.9-5 0Z" fill="#f8f4e8"/><path d="M2.7 2.8h5.6" stroke="#fffdf6" stroke-width=".6"/>'
    + '<path d="M7.6 4v7.3" stroke="#ddd5c2" stroke-width=".6"/>' + GLINT;
}

function sodaArtwork() {
  return '<rect x="2.5" y="2" width="6.4" height="10.6" rx="1" fill="#c65a4c" stroke="#8d3d34" stroke-width=".5"/>'
    + '<path d="M2.6 6h6.2v2.6H2.6Z" fill="#f1e3c6"/><path d="M4 7.3h3.4" stroke="#c65a4c" stroke-width=".6"/>'
    + '<ellipse cx="5.7" cy="2.1" rx="3.1" ry=".8" fill="#c9c8bd" stroke="#8f8e83" stroke-width=".35"/>'
    + '<path d="M5.2 1.8h1.2" stroke="#7d7c72" stroke-width=".4"/><path d="M3.4 3.4v8" stroke="#e48d80" stroke-width=".5"/>';
}

// One drink artwork, either a mug design index or a { kind, mug } lounge drink.
export function drinkArtwork(cup, x, y) {
  if (typeof cup !== "object" || cup === null) return mugArtwork(cup, x, y);
  const kind = DRINKS.includes(cup.kind) ? cup.kind : "coffee";
  if (kind === "coffee" || kind === "tea") {
    const mug = mugArtwork(cup.mug, x, y).replace('data-cup="', 'data-drink="' + kind + '" data-cup="');
    const inside = (kind === "tea" ? '<ellipse cx="5" cy="3.5" rx="2.7" ry=".7" fill="#b57a3e"/>'
      + '<path d="M6.4 3.4q1.6 1 1.4 3.6" fill="none" stroke="#efe7d4" stroke-width=".35"/><rect x="7.1" y="6.6" width="1.6" height="1.9" fill="#e7d6a8" stroke="#a88f5c" stroke-width=".3"/>' : '')
      + '<path class="stir-spoon" d="M4.3 3.6 6.6.4" stroke="#b9b6aa" stroke-width=".6" stroke-linecap="round"/>';
    return mug.replace(/<\/svg>$/, inside + '</svg>');
  }
  return '<svg class="coffee-cup" data-drink="' + kind + '" x="' + x + '" y="' + y + '" width="4.8" height="5.5" viewBox="0 0 12 14">'
    + (kind === "soda" ? sodaArtwork() : glassArtwork(kind)) + '</svg>';
}
