"""Play-test a generated game in a headless browser and say what is wrong with it.

run(path) returns a list of problems in plain English (empty = it plays), or None when no
browser library is installed. The forge sends the problems back to the model to fix.
"""
import random
from pathlib import Path

SAMPLE = """() => {
  const c = document.getElementById('c'); const x = c.getContext('2d');
  const d = x.getImageData(0, 60, c.width, c.height - 60).data;   // below the score strip
  let h = 0; const colours = new Set();
  for (let i = 0; i < d.length; i += 4 * 97) {
    h = (h * 31 + d[i] * 7 + d[i + 1] * 3 + d[i + 2]) % 1000000007;
    colours.add(d[i] + ',' + d[i + 1] + ',' + d[i + 2]);
  }
  return { hash: h, colours: colours.size };
}"""


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        try:
            from patchright.sync_api import sync_playwright
            return sync_playwright
        except ImportError:
            return None


def run(path, seconds=5, thumb=None):
    sync_playwright = _playwright()
    if sync_playwright is None:
        return None
    errors, problems = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 480, "height": 720})
        page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0][:200]))
        page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
        page.goto(Path(path).resolve().as_uri())
        page.wait_for_timeout(1500)
        if thumb:                       # before any input: the game as a new player first sees it
            page.screenshot(path=str(thumb))
        idle_over = page.evaluate("() => document.documentElement.dataset.forgeState === 'over'")
        first = page.evaluate(SAMPLE)
        keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space"]
        rng = random.Random(7)
        changed = False
        for i in range(seconds * 5):
            k = rng.choice(keys)
            page.keyboard.down(k)
            page.wait_for_timeout(120)
            page.keyboard.up(k)
            if i % 6 == 3:
                page.mouse.click(rng.randint(40, 440), rng.randint(200, 680))
            page.wait_for_timeout(80)
            if not changed and page.evaluate(SAMPLE)["hash"] != first["hash"]:
                changed = True
        later = page.evaluate(SAMPLE)
        # read through DOM attributes: patchright evaluates in an isolated world that cannot see
        # page globals like window.__forge, but it shares the DOM
        state = page.evaluate("""() => { const r = document.documentElement;
          if (r.dataset.forgeFrames === undefined) return { started: false, frames: 0, errors: JSON.parse(r.dataset.forgeErrors || "[]") };
          return { started: true, frames: +r.dataset.forgeFrames, errors: JSON.parse(r.dataset.forgeErrors || "[]") }; }""")
        browser.close()

    for e in state.get("errors", [])[:5]:
        problems.append("error: " + e)
    for e in errors[:5]:
        if not any(e[:40] in p for p in problems):
            problems.append("JavaScript error: " + e)
    if state.get("started") and idle_over:
        problems.append("the player loses within 1.5 seconds without touching anything - give them a safe start")
    if not state.get("started"):
        if not problems:
            problems.append("the engine never started - the script failed to parse")
        return problems
    if state.get("frames", 0) < 30:
        problems.append("the game loop barely ran (%d frames)" % state.get("frames", 0))
    if later["colours"] <= 1:
        problems.append("the play area is blank or a single flat colour - draw() is not drawing the game")
    if not changed:
        problems.append("nothing on screen moved during five seconds of play - update() or draw() is not animating")
    return problems
