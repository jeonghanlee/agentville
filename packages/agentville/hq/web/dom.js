// Element construction shared by views. Branch-provided strings become text nodes, never markup.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "style") {
      for (const [name, style] of Object.entries(value)) {
        if (name.startsWith("--")) node.style.setProperty(name, style); else node.style[name] = style;
      }
    }
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
export function button(label, cls, fn, attrs = {}) {
  const node = el("button", { type: "button", class: cls, ...attrs }, label);
  node.addEventListener("click", fn);
  return node;
}
