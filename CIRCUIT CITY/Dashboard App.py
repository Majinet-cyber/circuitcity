from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]
