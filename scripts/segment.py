"""Segment raw extracted text into content-type sections.

Reads raw_text.txt and splits it into labeled segments based on known
header markers from the SGMA booklet structure.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_TEXT_PATH = PROJECT_ROOT / "data" / "extracted" / "raw_text.txt"
OUTPUT_PATH = PROJECT_ROOT / "data" / "extracted" / "segments.json"

# Ordered list of (header_pattern, segment_type, label).
# Each segment runs from its header to the next header in this list.
SEGMENT_MARKERS = [
    ("INTRODUCTION", "explanatory", "Introduction"),
    ("CREDITS", "explanatory", "Credits"),
    ("THE STATUTES IN CONTEXT", "explanatory", "The Statutes in Context"),
    ("RECENT JUDICIAL DECISIONS", "cases", "Recent Judicial Decisions"),
    ("UNCODIFIED FINDINGS FROM THE ADOPTION OF SGMA", "findings", "Uncodified Findings"),
    (
        "SGMA-RELATED GOVERNMENT CODE PROVISIONS",
        "gov_code_sections",
        "Government Code Provisions",
    ),
    (
        "SGMA-RELATED WATER CODE PROVISIONS",
        "water_code_related_sections",
        "Related Water Code Provisions",
    ),
    (
        r"SGMA STATUTE .{1,3} WATER CODE",
        "water_code_sgma_sections",
        "SGMA Statute — Water Code",
    ),
    (
        r"SGMA REGULATIONS .{1,3} CODE OF REGULATIONS",
        "ccr_dwr_sections",
        "DWR Regulations",
    ),
    (
        r"DIVISION 3\.\s+STATE WATER RESOURCES CONTROL",
        "ccr_swrcb_sections",
        "SWRCB Regulations",
    ),
    (
        r"GROUNDWATER ADJUDICATIONS .{1,3} CODE OF CIVIL",
        "ccp_sections",
        "Groundwater Adjudications",
    ),
    (
        r"LEGISLATIVE HISTORY .{1,3} SGMA",
        "leg_history",
        "Legislative History",
    ),
]

# Lines that are page separators (rows of underscores)
SEPARATOR_RE = re.compile(r"^\s*_{20,}\s*$")

# Lines that are standalone page numbers (heavily indented number)
PAGE_NUM_RE = re.compile(r"^\s{20,}\d{1,3}\s*$")

# The TOC occupies the first ~456 lines. Content headers appear after this.
TOC_END_LINE = 450


def find_header_line(lines: list[str], pattern: str, start_from: int = TOC_END_LINE) -> int | None:
    """Find the line index where pattern appears in the content (after TOC)."""
    regex = re.compile(pattern, re.IGNORECASE)
    for i in range(start_from, len(lines)):
        stripped = lines[i].strip()
        if stripped and regex.search(stripped):
            return i
    return None


def clean_segment_text(lines: list[str]) -> str:
    """Remove page separators and standalone page numbers from segment lines."""
    cleaned = []
    for line in lines:
        if SEPARATOR_RE.match(line):
            continue
        if PAGE_NUM_RE.match(line):
            continue
        cleaned.append(line)

    # Strip leading/trailing blank lines
    text = "\n".join(cleaned)
    return text.strip()


def main() -> None:
    if not RAW_TEXT_PATH.exists():
        print(f"Error: raw text not found at {RAW_TEXT_PATH}", file=sys.stderr)
        print("Run extract_raw.py first.", file=sys.stderr)
        sys.exit(1)

    raw_text = RAW_TEXT_PATH.read_text()
    lines = raw_text.split("\n")
    total_lines = len(lines)
    print(f"Read {total_lines} lines from {RAW_TEXT_PATH}")

    # Find all header positions
    header_positions: list[tuple[int, str, str]] = []
    for pattern, seg_type, label in SEGMENT_MARKERS:
        line_idx = find_header_line(lines, pattern)
        if line_idx is None:
            print(f"Warning: header not found for pattern '{pattern}'", file=sys.stderr)
            continue
        header_positions.append((line_idx, seg_type, label))
        print(f"  Found '{label}' at line {line_idx}")

    if not header_positions:
        print("Error: no headers found — cannot segment", file=sys.stderr)
        sys.exit(1)

    # Sort by line number (should already be in order, but be safe)
    header_positions.sort(key=lambda x: x[0])

    # Build segments — each runs from its header line to the next header line
    segments: list[dict] = []
    for i, (start_line, seg_type, label) in enumerate(header_positions):
        if i + 1 < len(header_positions):
            end_line = header_positions[i + 1][0]
        else:
            end_line = total_lines

        segment_lines = lines[start_line:end_line]
        text = clean_segment_text(segment_lines)

        if not text:
            print(f"Warning: empty segment '{label}'", file=sys.stderr)

        segments.append(
            {
                "type": seg_type,
                "label": label,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": end_line - start_line,
                "char_count": len(text),
                "text": text,
            }
        )

    # Summary
    print(f"\nSegmented into {len(segments)} segments:")
    for seg in segments:
        print(f"  {seg['label']:40s}  type={seg['type']:30s}  lines={seg['line_count']:5d}  chars={seg['char_count']:6d}")

    total_chars = sum(s["char_count"] for s in segments)
    print(f"\nTotal characters across segments: {total_chars:,}")

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(segments, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
