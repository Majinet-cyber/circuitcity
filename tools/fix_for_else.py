from pathlib import Path
import re
from datetime import datetime

TAG_RE = re.compile(r"{%\s*(.*?)\s*%}", re.DOTALL)

def fix_text(text: str):
    out = []
    stack = []
    last = 0
    changed = False
    skip_mode = None  # "comment" or "verbatim"

    for m in TAG_RE.finditer(text):
        out.append(text[last:m.start()])

        token = (m.group(1) or "").strip()
        head = token.split()[0] if token.split() else ""
        tag_text = m.group(0)

        # keep everything untouched inside {% comment %} / {% verbatim %}
        if skip_mode:
            out.append(tag_text)
            if head == f"end{skip_mode}":
                skip_mode = None
            last = m.end()
            continue

        if head in ("comment", "verbatim"):
            skip_mode = head
            out.append(tag_text)
            last = m.end()
            continue

        # stack tracking (good enough for detecting "else while parsing for")
        if head == "for":
            stack.append("for")
        elif head == "if":
            stack.append("if")
        elif head in ("with", "block"):
            stack.append(head)
        elif head in ("endfor", "endif", "endwith", "endblock"):
            if stack:
                stack.pop()

        # THE FIX: {% else %} inside {% for %} becomes {% empty %}
        if head == "else" and stack and stack[-1] == "for":
            out.append("{% empty %}")
            changed = True
        else:
            out.append(tag_text)

        last = m.end()

    out.append(text[last:])
    return "".join(out), changed


def main():
    root = Path("templates")
    if not root.exists():
        print("No ./templates folder found. Run from project root.")
        return

    changed_files = 0
    for path in root.rglob("*.html"):
        original = path.read_text(encoding="utf-8", errors="ignore")
        fixed, changed = fix_text(original)
        if not changed:
            continue

        # backup once (or timestamp if already exists)
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = path.with_suffix(path.suffix + f".bak.{stamp}")

        bak.write_text(original, encoding="utf-8")
        path.write_text(fixed, encoding="utf-8")
        print(f"FIXED: {path} (backup -> {bak.name})")
        changed_files += 1

    if changed_files == 0:
        print("OK: No invalid '{% else %}' inside '{% for %}' found.")
    else:
        print(f"DONE: fixed {changed_files} file(s). Restart runserver.")

if __name__ == "__main__":
    main()
