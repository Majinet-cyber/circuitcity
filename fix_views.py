# fix_views.py  -- run from the "circuitcity" folder (where manage.py is one level below)
import pathlib, re, sys

p = pathlib.Path("inventory/views.py")
if not p.exists():
    print("Could not find inventory/views.py — run this from the circuitcity folder.")
    sys.exit(1)

src = p.read_text(encoding="utf-8")
bak = p.with_suffix(".py.bak")
bak.write_text(src, encoding="utf-8")

def strip_f_on_script_blocks(text: str) -> str:
    """
    Remove the 'f' from triple-quoted strings that contain <script ...> so braces
    inside JavaScript don't break Python's f-string parser.
    """
    out = []
    pos = 0
    # Prefix letters may be in any order (r, u, b, f, a). We care only about 'f'.
    pat = re.compile(r"(?is)\b([rubfa]{0,3})(\"\"\"|''')")

    while True:
        m = pat.search(text, pos)
        if not m:
            out.append(text[pos:])
            break

        start = m.start()
        out.append(text[pos:start])

        prefix = m.group(1)  # e.g., f, rf, fr, r, '', etc.
        q = m.group(2)       # ''' or """

        body_start = m.end()
        body_end = text.find(q, body_start)
        if body_end == -1:
            # unmatched triple quote -> append rest and stop
            out.append(text[start:])
            break

        body = text[body_start:body_end]
        new_prefix = prefix

        if "f" in prefix.lower() and "<script" in body.lower():
            # drop 'f' but keep r/u/b/a if present
            new_prefix = "".join(ch for ch in prefix if ch.lower() != "f")

        out.append(new_prefix + q + body + q)
        pos = body_end + len(q)

    return "".join(out)

def comment_top_level_js(text: str) -> str:
    """
    If there are stray JS lines (const/let/function/if(document...)) outside any
    triple-quoted string, comment them so the module can import.
    """
    res = []
    in_triple = False
    delim = None

    # detect start of a triple-quoted string
    start_pat = re.compile(r"(?is)\b([rubfa]{0,3})(\"\"\"|''')")

    for line in text.splitlines(keepends=True):
        if not in_triple:
            m = start_pat.search(line)
            if m:
                in_triple = True
                delim = m.group(2)
                res.append(line)
                continue

            stripped = line.lstrip()
            # obvious JS lines that break Python when not in a string
            if (
                stripped.startswith(("const ", "let ", "function ", "document.", "if("))
                or "replace(/\\D/g" in stripped
                or "<script" in stripped.lower()
                or "</script>" in stripped.lower()
            ):
                indent = line[: len(line) - len(stripped)]
                res.append(f"{indent}# JS_MOVED: {stripped}")
            else:
                res.append(line)
        else:
            res.append(line)
            if delim in line:
                in_triple = False
                delim = None

    return "".join(res)

# Apply fixes
step1 = strip_f_on_script_blocks(src)
step2 = comment_top_level_js(step1)

p.write_text(step2, encoding="utf-8")

print(f"Patched {p} (backup at {bak})")
