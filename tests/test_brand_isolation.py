from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
# Split so this file itself does not contain another brand's name.
BANNED = (
    "fant" + "zo",
    "ibe" + "tin",
    "bet" + "roxy",
    "dura" + "bet",
    "live" + " tv",
    "899266" + "4481",
)


def test_repo_has_no_other_brand_markers():
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".db"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").casefold()
        for marker in BANNED:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)}:{marker}")
    assert offenders == []
