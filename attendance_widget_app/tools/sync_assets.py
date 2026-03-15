from __future__ import annotations

import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = WORKSPACE_ROOT / "attendance_widget_app"
TARGET_ASSETS = PROJECT_ROOT / "assets"
TARGET_THUMBNAIL = TARGET_ASSETS / "thumbnail"

ASSET_FILES = [
    "back.png",
    "HP.png",
    "hog_gun.png",
    "hog_skill.png",
    "koverwatch.ttf",
    "occupation_blue.png",
    "occupation_red.png",
    "overwatch_blue_new.png",
    "overwatch_red_new.png",
    "Q_skill.png",
    "tab_bg_img.png",
]


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    TARGET_ASSETS.mkdir(parents=True, exist_ok=True)
    TARGET_THUMBNAIL.mkdir(parents=True, exist_ok=True)

    for name in ASSET_FILES:
        source = WORKSPACE_ROOT / name
        if not source.exists():
            if name == "hog_thumb.png":
                continue
            raise FileNotFoundError(f"Missing asset: {source}")
        copy_file(source, TARGET_ASSETS / name)

    source_thumbnail = WORKSPACE_ROOT / "thumbnail"
    if not source_thumbnail.exists():
        raise FileNotFoundError(f"Missing thumbnail directory: {source_thumbnail}")

    for existing in TARGET_THUMBNAIL.iterdir():
        if existing.is_file():
            existing.unlink()

    thumbnail_files = []
    for source in source_thumbnail.iterdir():
        if source.is_file():
            copy_file(source, TARGET_THUMBNAIL / source.name)
            thumbnail_files.append(source)

    fallback_thumb = TARGET_ASSETS / "hog_thumb.png"
    source_thumb = WORKSPACE_ROOT / "hog_thumb.png"
    if source_thumb.exists():
        copy_file(source_thumb, fallback_thumb)
    elif thumbnail_files:
        copy_file(sorted(thumbnail_files)[0], fallback_thumb)

    print(f"Synced assets to {TARGET_ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
