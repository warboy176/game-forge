"""Write games/index.html: a grid of every game in the folder, ready for GitHub Pages or itch.io."""
import html, json, sys
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Game Forge Arcade</title>
<style>
:root {{ --bg:#0b0d12; --card:#151924; --ink:#eef1f7; --dim:#8d95a8; --hot:#ff4b3e; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 system-ui, sans-serif; }}
header {{ padding:28px 20px 8px; max-width:1100px; margin:auto; }}
h1 {{ margin:0; font-size:30px; letter-spacing:.02em; }} h1 b {{ color:var(--hot); }}
p {{ color:var(--dim); margin:6px 0 0; }}
main {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:16px; padding:20px; max-width:1100px; margin:auto; }}
a {{ color:inherit; text-decoration:none; background:var(--card); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; }}
a:hover, a:focus-visible {{ outline:2px solid var(--hot); }}
img, .blank {{ width:100%; aspect-ratio:2/3; object-fit:cover; background:#1c2130; display:block; }}
span {{ padding:10px 12px; font-weight:600; }}
</style></head><body>
<header><h1>Game Forge <b>Arcade</b></h1><p>{n} games, each written by a local model and play-tested by a headless browser.</p></header>
<main>
{cards}
</main></body></html>
"""


def build(out="games"):
    root = Path(out)
    cards = []
    for g in sorted(root.glob("*/index.html")):
        meta = g.parent / "game.json"
        info = json.loads(meta.read_text()) if meta.exists() else {}
        if info.get("passed") is False:
            continue
        title = html.escape(info.get("title") or g.parent.name)
        thumb = g.parent / "thumb.png"
        pic = '<img src="%s/thumb.png" alt="">' % g.parent.name if thumb.exists() else '<div class="blank"></div>'
        cards.append('<a href="%s/index.html">%s<span>%s</span></a>' % (g.parent.name, pic, title))
    (root / "index.html").write_text(PAGE.format(n=len(cards), cards="\n".join(cards)), encoding="utf-8")
    return len(cards)


if __name__ == "__main__":
    print("gallery:", build(sys.argv[1] if len(sys.argv) > 1 else "games"), "games")
