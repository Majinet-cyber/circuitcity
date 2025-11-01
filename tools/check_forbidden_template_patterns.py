import sys, re, pathlib

# Disallow reading QueryDicts in templates (the bug you hit)
FORBIDDEN = [
    r"request\.GET",
    r"request\.POST",
]

def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = []
    for p in root.rglob("templates/**/*.html"):
        if not p.is_file(): 
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for pat in FORBIDDEN:
            if re.search(pat, txt):
                bad.append((p, pat))
    if bad:
        for p, pat in bad:
            print(f"Forbidden pattern '{pat}' in {p}")
        sys.exit(1)
    print("OK: templates clean")

if __name__ == "__main__":
    main()
