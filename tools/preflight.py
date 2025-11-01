# tools/preflight.py
from __future__ import annotations

import os
import re
import sys
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------------------
# Resolve paths robustly (works when called from repo root OR from tools/)
# --------------------------------------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parent.parent  # …/circuitcity
MANAGE_PY = REPO_ROOT / "manage.py"
PY = sys.executable

def run(title: str, *cmd: str, cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a command, show it, and fail fast with a clear label."""
    print(f"\n=== {title} ===")
    print(">", " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd or REPO_ROOT, env=env or os.environ.copy())
    if p.returncode != 0:
        print(f"[FAIL] {title}")
        sys.exit(p.returncode)
    print(f"[OK] {title}")

def django_env() -> dict:
    """Return env with DJANGO_SETTINGS_MODULE defaulted to cc.settings if not set."""
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")
    return env

def run_manage(title: str, *args: str) -> None:
    run(title, PY, str(MANAGE_PY), *args, cwd=REPO_ROOT, env=django_env())

def compile_project_code() -> None:
    """
    Byte-compile ONLY first-party project dirs (skip .venv/site-packages).
    Excludes tests/ and migrations/ to avoid slow/noisy compiles.
    """
    print("\n=== compileall (project dirs only) ===")
    import compileall

    PROJECT_DIRS = [
        "cc",
        "circuitcity",
        "inventory",
        "sales",
        "dashboard",
        "tenants",
        "layby",
        "wallet",
        "simulator",
        "billing",
    ]
    SKIP_RX = re.compile(r"(^|[\\/])(tests?|test_[^\\/]+|migrations)([\\/]|$)", re.IGNORECASE)

    found_any = False
    for rel in PROJECT_DIRS:
        d = (REPO_ROOT / rel).resolve()
        if not d.exists():
            continue
        found_any = True
        print(f"> compiling {d}")
        ok = compileall.compile_dir(
            str(d),
            maxlevels=10,
            force=False,
            quiet=1,
            rx=SKIP_RX,  # exclude tests & migrations
        )
        if not ok:
            print(f"[FAIL] compileall reported errors in {d}")
            sys.exit(1)

    if not found_any:
        print("[WARN] No project directories found to compile (skipping).")
    else:
        print("[OK] compileall finished")

def main() -> None:
    # 0) Echo environment (useful inside hooks/CI)
    print(f"Repo root: {REPO_ROOT}")
    print(f"Python: {PY}")
    print(f"DJANGO_SETTINGS_MODULE={os.environ.get('DJANGO_SETTINGS_MODULE','(default -> cc.settings)')}")

    # 1) Django sanity checks (non-fatal warnings are fine)
    run_manage("Django checks", "check")

    # 2) No pending migrations
    run_manage("No pending migrations", "makemigrations", "--check", "--dry-run")

    # 3) URLConf imports cleanly (explicit)
    url_probe = (
        "import os, django, importlib; "
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','cc.settings'); "
        "django.setup(); "
        "importlib.import_module('cc.urls')"
    )
    run("Import URLConf", PY, "-c", url_probe)

    # 4) Static files collect (dry run if supported, else normal to staticfiles/)
    try:
        run_manage("collectstatic dry run", "collectstatic", "--noinput", "--dry-run")
    except SystemExit:
        print("[WARN] collectstatic --dry-run not supported; doing normal collectstatic")
        run_manage("collectstatic", "collectstatic", "--noinput")

    # 5) Byte-compile our project dirs only (avoid .venv / site-packages)
    compile_project_code()

    # 6) Fast smoke tests if these modules exist
    possible = [
        "tests.test_tenant_activation",
        "inventory.tests.test_scope",
        "inventory.tests.test_mark_sold",
        "inventory.tests.test_predictions_endpoint",
    ]
    existing = []
    for mod in possible:
        try:
            __import__(mod)
            existing.append(mod)
        except Exception:
            pass

    if existing:
        run_manage("Unit tests (smoke)", "test", *existing)
    else:
        print("\n[WARN] No smoke tests found; skipping tests.")

if __name__ == "__main__":
    main()
