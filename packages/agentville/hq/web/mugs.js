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
