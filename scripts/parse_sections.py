"""Parse segments into individual code section records.

Reads segments.json and splits statute/regulation segments into individual
section records, producing the core dataset for the sections table.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEGMENTS_PATH = PROJECT_ROOT / "data" / "extracted" / "segments.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "extracted" / "sections.json"

# Map segment types to database fields
SEGMENT_TYPE_MAP = {
    "gov_code_sections": {"code": "gov_code", "content_type": "statute"},
    "water_code_related_sections": {"code": "water_code", "content_type": "statute"},
    "water_code_sgma_sections": {"code": "water_code", "content_type": "statute"},
    "ccr_dwr_sections": {"code": "ccr_title_23", "content_type": "regulation"},
    "ccr_swrcb_sections": {"code": "ccr_title_23", "content_type": "regulation"},
    "ccp_sections": {"code": "ccp", "content_type": "statute"},
}

# Hierarchy levels (lower number = broader scope)
HIERARCHY_LEVELS = {
    "title": 1,
    "division": 2,
    "part": 3,
    "chapter": 4,
    "subchapter": 5,
    "article": 6,
    "subarticle": 7,
}

# --- Regex patterns ---

# Section header: § followed by section number at start of line
# Uses [ \t]* instead of \s* to avoid matching across lines
SECTION_HEADER_RE = re.compile(
    r'^[ \t]*§[ \t]*(\d+(?:\.\d+)*)', re.MULTILINE
)

# Bracketed title for statutes: [Title Text] (may span multiple lines)
BRACKETED_TITLE_RE = re.compile(r'\[([^\]]*(?:\n[^\]]*)*)\]')

# Amendment history start for statutes (must be at start of line after newline)
AMENDMENT_START_RE = re.compile(
    r'\n\((?:Added|Amended|Repealed|Technical)\s'
)

# Note block start for regulations
NOTE_START_RE = re.compile(r'\nNote:[ \t]')

# Hierarchy header line (Division, Part, Chapter, Article, etc.)
# Handles "Chapter. 4.5" (period after keyword) seen in SWRCB regs
HIERARCHY_LINE_RE = re.compile(
    r'^[ \t]*(Title|Division|Part|Chapter|Subchapter|Article|Subarticle)'
    r'[ \t]*\.?[ \t]*(\d+(?:\.\d+)*)',
    re.IGNORECASE | re.MULTILINE,
)


def extract_statute_title(chunk: str) -> str:
    """Extract bracketed title [Title Text] from a statute section."""
    m = BRACKETED_TITLE_RE.search(chunk[:500])
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()
    return ""


def extract_regulation_title(chunk: str) -> str:
    """Extract title from regulation header (text after § NUMBER. on first line)."""
    first_newline = chunk.find('\n')
    if first_newline == -1:
        first_newline = len(chunk)
    first_line = chunk[:first_newline]

    m = re.match(r'[ \t]*§[ \t]*\d+(?:\.\d+)*\.?[ \t]*', first_line)
    if m:
        title = first_line[m.end():].strip()
        if title.endswith('.'):
            title = title[:-1].strip()
        return title
    return ""


def find_matching_close_paren(text: str, start: int, max_len: int = 1000) -> int:
    """Find the closing paren matching the opening paren at `start`.

    Returns position after the closing paren, or `start` if not found
    within max_len characters.
    """
    depth = 0
    end = min(start + max_len, len(text))
    for i in range(start, end):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
    return start


def extract_trailing_metadata(chunk: str, is_statute: bool) -> tuple[str, int]:
    """Extract amendment history (statutes) or Note block (regulations).

    Returns (metadata_text, content_end_position).
    content_end_position marks where section content ends (start of gap).
    """
    if is_statute:
        matches = list(AMENDMENT_START_RE.finditer(chunk))
        if matches:
            last = matches[-1]
            meta_start = last.start() + 1  # skip leading \n
            meta_end = find_matching_close_paren(chunk, meta_start)
            if meta_end > meta_start:
                return chunk[meta_start:meta_end].strip(), meta_end
    else:
        matches = list(NOTE_START_RE.finditer(chunk))
        if matches:
            last = matches[-1]
            meta_start = last.start() + 1  # skip leading \n
            remaining = chunk[meta_start:]
            blank = re.search(r'\n[ \t]*\n', remaining)
            meta_end = meta_start + blank.start() if blank else len(chunk)
            return chunk[meta_start:meta_end].strip(), meta_end

    # No metadata found — content extends to end of chunk
    return "", len(chunk)


def update_hierarchy(text: str, state: dict[int, str]) -> dict[int, str]:
    """Extract hierarchy headers from gap text and update hierarchy state.

    When a header at level N is found, levels > N are cleared.
    Returns a new dict (does not modify the input).
    """
    result = dict(state)

    for m in HIERARCHY_LINE_RE.finditer(text):
        keyword = m.group(1)
        level = HIERARCHY_LEVELS.get(keyword.lower())
        if level is None:
            continue

        # Get the full header line text
        line_start = m.start()
        line_end = text.find('\n', m.end())
        if line_end == -1:
            line_end = len(text)
        header_text = text[line_start:line_end].strip()

        # Accumulate continuation lines (indented non-keyword lines)
        pos = line_end
        while pos < len(text):
            next_newline = text.find('\n', pos + 1)
            if next_newline == -1:
                next_line = text[pos + 1:]
                next_newline = len(text)
            else:
                next_line = text[pos + 1:next_newline]

            stripped = next_line.strip()
            if not stripped:
                break
            if stripped.startswith('§'):
                break
            if re.match(r'\*{3}$', stripped):
                break
            if HIERARCHY_LINE_RE.match(next_line):
                break
            header_text += ' ' + stripped
            pos = next_newline

        # Normalize whitespace
        header_text = re.sub(r'\s+', ' ', header_text).strip()

        # Set this level and clear all lower levels
        result[level] = header_text
        for l in list(result.keys()):
            if l > level:
                del result[l]

    return result


def parse_segment(segment: dict) -> list[dict]:
    """Parse a segment into individual section records."""
    text = segment["text"]
    seg_type = segment["type"]
    config = SEGMENT_TYPE_MAP[seg_type]
    code = config["code"]
    content_type = config["content_type"]
    is_statute = content_type == "statute"

    # Find all section headers
    matches = list(SECTION_HEADER_RE.finditer(text))
    if not matches:
        print(f"  Warning: no sections found in {seg_type}", file=sys.stderr)
        return []

    # Extract hierarchy from preamble (text before first §)
    preamble = text[:matches[0].start()]
    hierarchy = update_hierarchy(preamble, {})

    sections = []
    for i, match in enumerate(matches):
        # Raw chunk: from this § to the next § (or end of segment)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]

        section_number = match.group(1)

        # Extract title
        if is_statute:
            title = extract_statute_title(chunk)
        else:
            title = extract_regulation_title(chunk)

        # Extract trailing metadata and find content boundary
        amendment_history, content_end = extract_trailing_metadata(
            chunk, is_statute
        )

        # Full text: section content up to end of metadata, cleaned
        full_text = chunk[:content_end].strip()

        # Gap text (after content, before next §) — used for hierarchy
        gap = chunk[content_end:]

        # Record section with current hierarchy state
        hierarchy_context = [hierarchy[k] for k in sorted(hierarchy.keys())]

        sections.append({
            "section_number": section_number,
            "code": code,
            "content_type": content_type,
            "title": title,
            "full_text": full_text,
            "amendment_history": amendment_history,
            "hierarchy_context": hierarchy_context,
            "source_segment": seg_type,
        })

        # Update hierarchy from gap for next section
        hierarchy = update_hierarchy(gap, hierarchy)

    return sections


def validate_sections(sections: list[dict]) -> bool:
    """Validate parsed sections. Returns True if no errors found."""
    ok = True

    # Check for duplicates
    seen: set[tuple[str, str]] = set()
    for s in sections:
        key = (s["code"], s["section_number"])
        if key in seen:
            print(
                f"  ERROR: duplicate ({s['code']}, § {s['section_number']})",
                file=sys.stderr,
            )
            ok = False
        seen.add(key)

    # Check required fields
    for s in sections:
        if not s["section_number"]:
            print(f"  ERROR: missing section_number", file=sys.stderr)
            ok = False
        if not s["full_text"]:
            print(
                f"  ERROR: empty full_text for § {s['section_number']}",
                file=sys.stderr,
            )
            ok = False
        if not s["title"]:
            print(
                f"  Warning: missing title for {s['code']} "
                f"§ {s['section_number']}",
                file=sys.stderr,
            )
        if s["content_type"] == "statute" and not s["amendment_history"]:
            print(
                f"  Warning: missing amendment_history for {s['code']} "
                f"§ {s['section_number']}",
                file=sys.stderr,
            )

    return ok


def main() -> None:
    if not SEGMENTS_PATH.exists():
        print(f"Error: segments not found at {SEGMENTS_PATH}", file=sys.stderr)
        print("Run segment.py first.", file=sys.stderr)
        sys.exit(1)

    segments = json.loads(SEGMENTS_PATH.read_text())
    print(f"Read {len(segments)} segments from {SEGMENTS_PATH}")

    all_sections: list[dict] = []
    for segment in segments:
        if segment["type"] not in SEGMENT_TYPE_MAP:
            continue
        sections = parse_segment(segment)
        print(
            f"  {segment['type']:40s}  sections: {len(sections)}"
        )
        all_sections.extend(sections)

    # Summary by code
    print(f"\nTotal sections: {len(all_sections)}")
    by_code: dict[str, int] = {}
    for s in all_sections:
        by_code[s["code"]] = by_code.get(s["code"], 0) + 1
    for code, count in sorted(by_code.items()):
        print(f"  {code:20s}  {count}")

    # Validate
    print("\nValidation:")
    if not validate_sections(all_sections):
        print("\nValidation failed — output not written.", file=sys.stderr)
        sys.exit(1)
    print("  All checks passed.")

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(all_sections, indent=2, ensure_ascii=False)
    )
    print(f"\nWrote {len(all_sections)} sections to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
