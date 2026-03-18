"""Generate a manual sample list from limited dataset prefixes.

Usage:
    python scripts/generate_manual_sample_list.py
"""
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "data" / "Training" / "01.원천데이터" / "TS_지방행정기관"
LABEL_BASE_DIR = PROJECT_ROOT / "data" / "Training" / "02.라벨링데이터"
OUTPUT_FILE = PROJECT_ROOT / "data" / "samples" / "manual_20_samples.json"

LABEL_FOLDERS = {
    "classification": "TL_지방행정기관_분류",
    "summary": "TL_지방행정기관_요약",
    "qa": "TL_지방행정기관_질의응답",
}


def get_first_n_files(directory: Path, n: int):
    if not directory.exists():
        return []
    files = [p.name for p in sorted(directory.iterdir(), key=lambda p: p.name) if p.is_file()]
    return files[:n]


def main():
    SOURCE_COUNT = 40
    LABEL_COUNT = 10

    source_files = get_first_n_files(SOURCE_DIR, SOURCE_COUNT)
    if not source_files:
        raise RuntimeError(f"Source folder not found or empty: {SOURCE_DIR}")

    label_samples = {}
    for label_name, label_folder in LABEL_FOLDERS.items():
        folder_path = LABEL_BASE_DIR / label_folder
        label_files = get_first_n_files(folder_path, LABEL_COUNT)
        label_samples[label_name] = label_files

    manual_list = {
        "metadata": {
            "source_dir": str(SOURCE_DIR),
            "label_base_dir": str(LABEL_BASE_DIR),
            "source_count": len(source_files),
            "label_counts": {k: len(v) for k, v in label_samples.items()},
        },
        "sources": source_files,
        "labels": label_samples,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(manual_list, f, ensure_ascii=False, indent=2)

    print(f"Wrote manual sample list to: {OUTPUT_FILE}")
    print(f"Sources: {len(source_files)} files")
    for key, files in label_samples.items():
        print(f"{key}: {len(files)} files")


if __name__ == "__main__":
    main()
