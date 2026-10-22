import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "packages" / "agentville" / "hq" / "web"
# Window properties a page module could shadow by accident; a module binding of the same name hides the global
# for the whole module, and touching it before its declaration throws.
GLOBALS = {"history", "location", "name", "status", "top", "parent", "self", "window", "document", "navigator",
           "screen", "frames", "length", "closed", "opener", "origin", "event", "print", "open", "close", "stop",
           "focus", "blur", "find", "scroll", "fetch", "performance", "crypto", "localStorage", "sessionStorage",
           "caches", "external", "menubar", "toolbar", "statusbar", "visualViewport", "customElements"}


def _top_level_names(source):
    names = set()
    for line in source.splitlines():
        declaration = re.match(r"^(?:export\s+)?(?:let|const|var)\s+(.*)$", line)
        if declaration:
            names |= set(re.findall(r"(?:^|,)\s*([A-Za-z_$][\w$]*)\s*=", declaration.group(1)))
            continue
        function = re.match(r"^(?:export\s+)?(?:async\s+)?(?:function\*?|class)\s+([A-Za-z_$][\w$]*)", line)
        if function:
            names.add(function.group(1))
    return names


def test_top_level_names_do_not_shadow_window_globals():
    assert _top_level_names("let history = null, replay = null;\nfunction status() {}") == {"history", "replay", "status"}
    for path in sorted(WEB.glob("*.js")):
        assert _top_level_names(path.read_text(encoding="utf-8")) & GLOBALS == set(), path.name
