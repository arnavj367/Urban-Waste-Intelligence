from pathlib import Path

def ensure_dirs(root: Path):
    for name in ("data", "uploads", "models"):
        (root / name).mkdir(parents=True, exist_ok=True)

def status_badge(status):
    return status
