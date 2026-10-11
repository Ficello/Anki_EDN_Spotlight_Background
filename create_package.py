import os
import zipfile

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_PATH = os.path.join(SOURCE_DIR, "Anki_EDN_Spotlight_Background.ankiaddon")

EXCLUDES = [
    "__pycache__",
    "meta.json",
    "cache",
    "favorites",
    "current_background.jpg",
    "spotlight.json",
    ".git",
    ".gitignore",
    ".vscode",
    ".idea",
    ".ankiaddon",
    ".log"
]

def should_exclude(rel_path):
    parts = rel_path.split(os.sep)
    for part in parts:
        for exclude in EXCLUDES:
            if exclude == part or (exclude.startswith(".") and part.endswith(exclude)):
                return True
    return False

def create_addon_package():
    print(f"Packaging addon from: {SOURCE_DIR}")
    print(f"Destination: {DEST_PATH}")

    with zipfile.ZipFile(DEST_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if not should_exclude(os.path.relpath(os.path.join(root, d), SOURCE_DIR))]
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, SOURCE_DIR)
                if should_exclude(rel_path) or file == "create_package.py":
                    continue
                print(f"Adding: {rel_path}")
                zipf.write(abs_path, rel_path)

    print("\nPackage created successfully!")

if __name__ == "__main__":
    create_addon_package()
