import subprocess, sys, os, shutil

PY = r".\.venv\Scripts\python.exe" if os.name == "nt" else "python"

def run(title, *cmd):
    print(f"\n==> {title}")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)

# 1) working tree status (informational)
run("git status", "git", "status", "--porcelain")

# 2) Django system checks (prod-grade flags too)
run("django check --deploy", PY, "manage.py", "check", "--deploy")

# 3) Compile all .py (catches stray brackets / syntax)
run("compileall", PY, "-m", "compileall", "-q", ".")

# 4) Migrations drift (block if missing)
run("makemigrations --check", PY, "manage.py", "makemigrations", "--check", "--dry-run")
run("migrate --plan", PY, "manage.py", "migrate", "--plan")

# 5) Template safety scan
run("template guard", PY, "tools/check_forbidden_template_patterns.py")

# 6) Smoke tests if pytest exists
if shutil.which(f"{PY}") and (os.path.isdir("tests") or os.path.exists("pytest.ini")):
    run("pytest -q", PY, "-m", "pytest", "-q")

print("\nPreflight OK ✅")
