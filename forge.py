#!/usr/bin/env python3
"""game-forge: one line of idea in, one playable HTML5 game out.

  python forge.py "a snake that is a freight train"        # one game
  python forge.py --batch ideas.txt                         # one game per line
  python forge.py --invent 10 --theme "deep sea"            # let the model pitch the ideas too

Any OpenAI-compatible endpoint works: Ollama (default), llama.cpp server, LM Studio, vLLM,
or a hosted API. Every game is play-tested in a headless browser; failures go back to the
model with the exact errors until it passes or runs out of retries.
"""
import argparse, html, json, os, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check, gallery

TEMPLATE = (HERE / "template.html").read_text(encoding="utf-8")
SYSTEM = (HERE / "prompt.md").read_text(encoding="utf-8")
BANNED = [(r"\bimport\s", "uses import"), (r"\bfetch\s*\(|XMLHttpRequest|https?://", "reaches the network"),
          (r"\bdocument\.|\bwindow\.", "touches the DOM"), (r"\balert\s*\(", "uses alert()"),
          (r"localStorage", "uses localStorage"), (r"new\s+(Image|Audio)\b", "loads images or audio")]


def chat(args, messages):
    body = {"model": args.model, "messages": messages, "temperature": args.temperature, "stream": False}
    req = urllib.request.Request(args.endpoint.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + args.api_key} if args.api_key else {})})
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def extract_code(reply):
    blocks = re.findall(r"```(?:javascript|js)?[ \t]*\n(.*?)```", reply, re.S)
    return (max(blocks, key=len) if blocks else reply).strip()


def static_problems(code):
    out = []
    if not re.search(r"\bconst\s+GAME\s*=", code):
        out.append("there is no `const GAME = {...}` definition")
    for name in ("init", "update", "draw"):
        if not re.search(r"\b%s\s*\(" % name, code):
            out.append("GAME has no %s() method" % name)
    for pattern, why in BANNED:
        if re.search(pattern, code):
            out.append("the code " + why + ", which the engine forbids")
    if re.search(r"fillText\([^;]*(score|game\s*over)", code, re.I):
        out.append("the code draws its own score or game-over text; the engine already draws both, remove yours")
    return out


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "game"


def forge(idea, args):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Game idea: " + idea}]
    t0, problems, attempt = time.time(), ["not generated"], 0
    folder = None
    for attempt in range(1, args.retries + 2):
        reply = chat(args, messages)
        code = extract_code(reply)
        m = re.search(r"title\s*:\s*[\"'`]([^\"'`]{2,60})[\"'`]", code)
        title = m.group(1).strip() if m else idea[:40]
        if folder is None:
            folder = Path(args.out) / slug(title)
            n = 2
            while folder.exists():
                folder = Path(args.out) / ("%s-%d" % (slug(title), n)); n += 1
            folder.mkdir(parents=True)
        game_line = TEMPLATE.split("/*{{GAME}}*/")[0].count("\n") + 1
        page = (TEMPLATE.replace("{{TITLE}}", html.escape(title)).replace("{{GAME_LINE}}", str(game_line))
                .replace("/*{{GAME}}*/", code))
        (folder / "index.html").write_text(page, encoding="utf-8")
        problems = static_problems(code)
        if not problems and not args.no_check:
            found = check.run(folder / "index.html", thumb=folder / "thumb.png")
            if found is None:
                print("  (no browser library installed - skipping play-test; pip install playwright)")
            else:
                problems = found
        print("  attempt %d: %s" % (attempt, "PASS" if not problems else "; ".join(problems[:3])), flush=True)
        if not problems:
            break
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "Automated play-testing found these problems:\n- " + "\n- ".join(problems)
                      + "\nFix every one. Reply with the complete corrected code in one ```js block."}]
    info = {"idea": idea, "title": title, "passed": not problems, "attempts": attempt,
            "problems": problems, "model": args.model, "seconds": round(time.time() - t0, 1)}
    (folder / "game.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


def invent(args, n, theme):
    ask = ("Pitch %d different small arcade game ideas%s. Each must be playable in under a minute on a phone "
           "with one thumb. One idea per line, one sentence each, no numbering, nothing else." %
           (n, (" themed around " + theme) if theme else ""))
    reply = chat(args, [{"role": "user", "content": ask}])
    lines = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", l).strip() for l in reply.splitlines()]
    return [l for l in lines if len(l) > 12][:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idea", nargs="?", help="one game idea, in plain words")
    ap.add_argument("--batch", help="text file, one idea per line")
    ap.add_argument("--invent", type=int, default=0, help="have the model pitch N ideas, then build them")
    ap.add_argument("--theme", default="", help="theme for --invent")
    ap.add_argument("--endpoint", default=os.environ.get("FORGE_ENDPOINT", "http://localhost:11434/v1"))
    ap.add_argument("--model", default=os.environ.get("FORGE_MODEL", "qwen2.5-coder:14b"))
    ap.add_argument("--api-key", default=os.environ.get("FORGE_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    ap.add_argument("--retries", type=int, default=3, help="repair rounds after a failed play-test")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default="games")
    ap.add_argument("--no-check", action="store_true", help="skip the headless play-test")
    args = ap.parse_args()

    ideas = []
    if args.idea:
        ideas.append(args.idea)
    if args.batch:
        ideas += [l.strip() for l in Path(args.batch).read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
    if args.invent:
        ideas += invent(args, args.invent, args.theme)
    if not ideas:
        ap.error("give an idea, --batch FILE or --invent N")

    results = []
    for i, idea in enumerate(ideas, 1):
        print("[%d/%d] %s" % (i, len(ideas), idea), flush=True)
        try:
            results.append(forge(idea, args))
        except Exception as e:
            print("  failed:", e, flush=True)
            results.append({"idea": idea, "passed": False, "problems": [str(e)]})
    passed = sum(1 for r in results if r.get("passed"))
    print("\n%d of %d games passed play-testing" % (passed, len(results)))
    print("gallery: %s/index.html (%d games)" % (args.out, gallery.build(args.out)))


if __name__ == "__main__":
    main()
