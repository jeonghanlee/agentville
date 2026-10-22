import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "packages" / "agentville" / "hq" / "web"


def _dictionary():
    sections, current = {}, None
    for line in (WEB / "i18n.js").read_text(encoding="utf-8").splitlines():
        section = re.match(r"^  (\w+): \{$", line)
        if section:
            current = sections.setdefault(section.group(1), {})
            continue
        entry = re.match(r'^\s+"([^"]+)":\s*"((?:[^"\\]|\\.)*)",?\s*$', line)
        if entry and current is not None:
            current[entry.group(1)] = json.loads(f'"{entry.group(2)}"')
    return sections


def test_english_and_korean_have_the_same_keys():
    sections = _dictionary()
    assert set(sections) == {"en", "ko"}
    assert set(sections["en"]) == set(sections["ko"])


def test_literal_keys_used_by_the_page_exist():
    english = _dictionary()["en"]
    used = set()
    for path in WEB.glob("*.js"):
        used |= set(re.findall(r'\bt\("([\w.]+)"[,)]', path.read_text(encoding="utf-8")))
    page = (WEB / "index.html").read_text(encoding="utf-8")
    used |= set(re.findall(r'data-i18n="([\w.]+)"', page))
    for pairs in re.findall(r'data-i18n-attr="([^"]+)"', page):
        used |= {pair.split("=")[1].strip() for pair in pairs.split(",")}
    assert used - set(english) == set()
