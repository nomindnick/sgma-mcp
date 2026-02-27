"""Extract raw text from the SGMA booklet PDF using pdftotext -layout."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_ROOT / "data" / "source-material" / "2-26-2025-sgma-booklet.pdf"
OUTPUT_PATH = PROJECT_ROOT / "data" / "extracted" / "raw_text.txt"


def main() -> None:
    if not PDF_PATH.exists():
        print(f"Error: PDF not found at {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["pdftotext", "-layout", str(PDF_PATH), str(OUTPUT_PATH)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error: pdftotext failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    text = OUTPUT_PATH.read_text()
    line_count = text.count("\n")
    char_count = len(text)

    print(f"Extracted {line_count} lines ({char_count:,} characters) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
