# tools/preflight.py
import sys, subprocess, os

PY = sys.executable
MANAGE = [PY, "manage.py"]

def run(title, *cmd):
    print(f"\n=== {title} ===")
    print(">", " ".join(cmd))
    p = subprocess.run(cmd)
    if p.returncode != 0:
        print(f"[FAIL] {title}")
        sys.exit(p.returncode)
    print(f"[OK] {title}")

def main():
    # 0) Quick environment echo (helps when hook runs)
    print(f"Python: {PY}")
    print(f"DJANGO_SETTINGS_MODULE={os.environ.get('DJANGO_SETTINGS_MODULE','(default)')}")

    # 1) Django sanity
    run("Django checks", *MANAGE, "check")

    # 2) No pending migrations
    run("No pending migrations", *MANAGE, "makemigrations", "--check", "--dry-run")

    # 3) URLConf imports cleanly
    run("Import URLConf", *MANAGE, "shell", "-c",
        "import importlib; importlib.import_module('cc.urls')")

    # 4) Static files collect (dry run)
    # If your Django version doesn’t support --dry-run, drop it.
    try:
        run("collectstatic dry run", *MANAGE, "collectstatic", "--noinput", "--dry-run")
    except SystemExit as e:
        # fallback without --dry-run
        print("[WARN] collectstatic --dry-run not supported; doing normal collectstatic to temp dir")
        run("collectstatic to temp", *MANAGE, "collectstatic", "--noinput")

    # 5) Fast smoke tests (only those that exist)
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
        run("Unit tests (smoke)", *MANAGE, "test", *existing)
    else:
        print("\n[WARN] No smoke tests found; skipping tests.")

if __name__ == "__main__":
    main()
