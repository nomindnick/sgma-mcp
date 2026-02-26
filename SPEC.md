# SGMA MCP Server — Specification

## Overview

This project creates an MCP (Model Context Protocol) server that provides Claude with authoritative, searchable access to California's SGMA legal corpus. The server wraps a structured SQLite database containing statutes, regulations, case law, definitions, and related legal resources, exposing them through MCP tools optimized for legal research workflows.

The primary user is a California public agency attorney doing SGMA work for a Groundwater Sustainability Agency (GSA) client. The tool transforms Claude from "smart but unreliable on legal citations" to "smart and citable" by grounding its legal reasoning in exact statutory and regulatory text.

## What We're Building

### The Database

A SQLite database containing:

1. **Code sections** — The full text of every statutory and regulatory section relevant to SGMA:
   - Water Code Part 2.74 (§§ 10720-10738) — the core SGMA statute
   - Related Water Code provisions (fees, extraction reporting, enforcement, monitoring)
   - Government Code provisions (planning/zoning groundwater requirements)
   - Title 23 CCR regulations (DWR GSP regulations, SWRCB implementation regulations)
   - Code of Civil Procedure (groundwater adjudication, §§ 830-852)

2. **Case law** — Initially the ~10 key cases cited in the SWRCB booklet with holdings summaries. Expandable to full case texts.

3. **Definitions** — Defined terms from both the statute (Water Code § 10721) and regulations (23 CCR § 351), linked to their source sections.

4. **Cross-references** — Relationships between provisions: which regulations implement which statutes, which cases interpret which sections.

5. **Supplementary content** — Explanatory text on SGMA history and groundwater common law, uncodified legislative findings, legislative history of amendments.

6. **Search infrastructure** — FTS5 full-text index and vector embeddings for hybrid search across all content.

### The MCP Server

A Python MCP server exposing these tools:

| Tool | Purpose | Backed By |
|---|---|---|
| `lookup_section` | Retrieve exact text by code and section number | Direct SQL |
| `search` | Find relevant provisions by natural language query | Hybrid FTS5 + embedding similarity |
| `get_definition` | Look up SGMA defined terms | Definitions table + FTS |
| `get_related` | Find cross-referenced and related provisions | Cross-references table |
| `list_structure` | Browse the organizational hierarchy | Hierarchy query |

### The Deployment

Deployed on Railway using HTTP+SSE transport, accessible to Claude Code and Claude Desktop as a remote MCP server.

## Data Sources

### Primary Source: SWRCB SGMA Booklet (January 2025)

`data/source-material/2-26-2025-sgma-booklet.pdf`

Published by the State Water Resources Control Board's Office of Chief Counsel. Contains:

| Content | PDF Pages | Content Type |
|---|---|---|
| Introduction and credits | 1 | Explanatory |
| History, common law, Winters doctrine | 2-5 | Explanatory |
| Recent judicial decisions | 6 | Cases |
| Uncodified legislative findings | 7-9 | Findings |
| Government Code provisions | 10-15 | Statute sections |
| Related Water Code provisions | 16-28 | Statute sections |
| SGMA statute (Water Code Part 2.74) | 29-99 | Statute sections |
| Title 23 CCR regulations (DWR) | 100-158 | Regulation sections |
| Title 23 CCR regulations (SWRCB) | 159-167 | Regulation sections |
| Code of Civil Procedure (adjudication) | 168-198 | Statute sections |
| Legislative history | 199-203 | Legislative history |

The booklet covers law as in effect January 1, 2025. The leginfo.legislature.ca.gov website blocks crawlers (`Disallow: /` in robots.txt), making the booklet the most practical authoritative source for bulk extraction.

The PDF has a clean text layer (ADA-compliant government document) and extracts well with `pdftotext -layout`.

### Future Sources (planned for later phases)

- Full case opinion texts
- DWR Best Management Practices documents
- DWR GSP evaluation/assessment staff reports
- SWRCB orders and resolutions
- DWR Bulletin 118 basin information
- Agency-specific documents (GSPs, MOUs, board resolutions)

## Data Model

### `sections` — Statutes and regulations

The core table. Statutes and regulations are structurally identical (numbered code sections with hierarchy) and belong together.

```sql
CREATE TABLE sections (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,              -- water_code | gov_code | ccr_title_23 | ccp
    section_number TEXT NOT NULL,    -- e.g., "10727.2", "354.28"
    title TEXT,                      -- bracketed title from booklet
    full_text TEXT NOT NULL,         -- verbatim section text
    hierarchy_path TEXT,             -- e.g., "Div 6 / Part 2.74 / Ch 6 / Art 1"
    content_type TEXT NOT NULL,      -- statute | regulation
    amendment_history TEXT,          -- e.g., "Added by Stats. 2014, Ch. 346..."
    effective_date TEXT,
    UNIQUE(code, section_number)
);
```

### `cases` — Case law

```sql
CREATE TABLE cases (
    id INTEGER PRIMARY KEY,
    case_name TEXT NOT NULL,         -- e.g., "City of Barstow v. Mojave Water Agency"
    citation TEXT,                   -- e.g., "(2000) 23 Cal.4th 1224"
    year INTEGER,
    court TEXT,                      -- e.g., "Cal. Supreme Court"
    summary TEXT,                    -- holding summary (always present)
    full_text TEXT,                  -- NULL initially, populated when full opinions added
    status TEXT DEFAULT 'good_law'   -- good_law | superseded | limited
);
```

### `definitions` — SGMA defined terms

```sql
CREATE TABLE definitions (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,              -- e.g., "basin", "de minimis extractor"
    definition_text TEXT NOT NULL,
    source_section_id INTEGER NOT NULL REFERENCES sections(id)
);
```

### `cross_references` — Relationships between provisions

```sql
CREATE TABLE cross_references (
    id INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL,         -- section | case | guidance | evaluation
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    relationship TEXT NOT NULL       -- implements | interprets | references | evaluates | supersedes
);
```

### `guidance_documents` — DWR/SWRCB guidance, BMPs, orders

```sql
CREATE TABLE guidance_documents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,            -- dwr | swrcb | other
    document_type TEXT NOT NULL,     -- bmp | bulletin | order | resolution | guidance
    title TEXT NOT NULL,
    date TEXT,
    full_text TEXT,
    metadata JSON                   -- flexible for source-specific fields
);
```

### `evaluations` — DWR GSP evaluations

```sql
CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY,
    basin_name TEXT NOT NULL,
    basin_number TEXT,               -- DWR basin ID
    gsa_name TEXT,
    plan_type TEXT,                  -- gsp | alternative | interim
    evaluation_date TEXT,
    determination TEXT,              -- approved | incomplete | inadequate
    full_text TEXT
);
```

### `agency_documents` — User's GSA materials

```sql
CREATE TABLE agency_documents (
    id INTEGER PRIMARY KEY,
    document_type TEXT NOT NULL,     -- gsp | mou | resolution | policy
    title TEXT NOT NULL,
    date TEXT,
    full_text TEXT,
    metadata JSON
);
```

### `auxiliary_content` — Explanatory text, findings, legislative history

```sql
CREATE TABLE auxiliary_content (
    id INTEGER PRIMARY KEY,
    content_type TEXT NOT NULL,      -- explanatory | finding | leg_history
    title TEXT,
    text TEXT NOT NULL,
    metadata JSON
);
```

### `chunks` — Unified search table (embeddings + FTS)

All searchable content is chunked and embedded here, regardless of source table.

```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,       -- section | case | guidance | evaluation | agency | auxiliary
    source_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    chunk_heading TEXT,              -- subdivision label, case section heading, etc.
    embedding BLOB                   -- vector stored via sqlite-vec
);

-- FTS5 virtual table for keyword search
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_text,
    content='chunks',
    content_rowid='id'
);
```

## Search Architecture

Three retrieval mechanisms, used in combination:

### 1. Citation Lookup (exact match)

Pattern: `lookup_section("water_code", "10727.2")` → direct SQL query on `sections` table.

Used when Claude already knows the specific section it needs. Fast and deterministic.

### 2. Full-Text Keyword Search (FTS5)

Pattern: `search("minimum threshold subsidence")` → FTS5 query on `chunks_fts`.

Best for queries using specific statutory terminology. Handles phrase queries and boolean operators. Returns ranked results.

### 3. Semantic Search (embeddings)

Pattern: `search("what authority does a GSA have to regulate extractions")` → vector similarity on `chunks.embedding`.

Best for natural language questions where the query doesn't use the same terminology as the statute. Finds conceptually related provisions.

### Hybrid Search Flow

The `search` tool combines mechanisms 2 and 3:

1. Check if query looks like a citation (regex for `§ XXXXX` patterns) → redirect to direct lookup
2. Run FTS5 keyword search → ranked results with BM25 scores
3. Run embedding similarity search → ranked results with cosine similarity scores
4. Merge and deduplicate, weighting both signals
5. Join results back to source tables for full metadata
6. Return ranked results with source type, citation, text snippet, and relevance score

### Chunking Strategy

- **Section-level embedding** for every section (chunk_index = 0, full section text)
- **Subdivision-level embeddings** for sections exceeding ~500 tokens — each major subdivision (a), (b), (c) etc. gets its own chunk, tagged with the parent section for context
- **Paragraph-level chunks** for long-form content (case opinions, guidance documents, explanatory text)

## Extraction Pipeline

The pipeline transforms the SGMA booklet PDF into a populated SQLite database through a series of scripts, each producing a checkpointed JSON artifact.

```
PDF
 → [extract_raw.py]      → data/extracted/raw_text.txt
 → [segment.py]           → data/extracted/segments.json
 → [parse_sections.py]    → data/extracted/sections.json
 → [parse_supplementary.py] → data/extracted/cases.json
                              data/extracted/explanatory.json
                              data/extracted/findings.json
                              data/extracted/leg_history.json
 → [enrich_sections.py]   → data/extracted/structured_sections.json
 → [load_database.py]     → data/sgma.db
 → [generate_embeddings.py] → data/sgma.db (with embeddings populated)
```

Each checkpoint is a reviewable file. If issues are found at any stage, fix the upstream script and re-run from that checkpoint.

After each pipeline step, a validation subagent runs automated checks (counts, formats, spot-checks against source) and produces a validation report. Human review is a second-pass option, not a bottleneck.

## MCP Tools

### `lookup_section(code: str, section_number: str) -> Section`

Retrieve the exact text of a specific code section by citation.

- `code`: One of `water_code`, `gov_code`, `ccr_title_23`, `ccp`
- `section_number`: e.g., `"10727.2"`, `"354.28"`, `"830"`
- Returns: Full section text, title, hierarchy path, amendment history

### `search(query: str, source_types: list[str] | None, limit: int = 10) -> list[SearchResult]`

Hybrid keyword + semantic search across all content.

- `query`: Natural language query or keyword terms
- `source_types`: Optional filter — `["section", "case", "guidance", "evaluation", "agency", "auxiliary"]`
- Returns: Ranked results with source type, citation/title, text snippet, relevance score

### `get_definition(term: str) -> list[Definition]`

Look up SGMA defined terms.

- `term`: The term to look up (e.g., `"basin"`, `"de minimis extractor"`)
- Returns: Definition text and source section for each match (may return multiple — statute and regulation definitions can differ)

### `get_related(code: str, section_number: str) -> RelatedProvisions`

Find provisions related to a given section via cross-references.

- Returns: Implementing regulations, authorizing statutes, interpreting cases, and referencing provisions, grouped by relationship type

### `list_structure(code: str | None, chapter: str | None) -> list[StructureEntry]`

Browse the organizational hierarchy of the code.

- With no arguments: returns top-level structure (codes → divisions → parts)
- With `code`: returns chapters/articles for that code
- With `code` and `chapter`: returns sections in that chapter
- Returns: Hierarchical outline with section numbers and titles

## Deployment

### Railway Configuration

- Python application with HTTP+SSE MCP transport
- SQLite database bundled in Docker image (no external database service)
- Environment variables for OpenAI API key (embeddings)
- No persistent storage needed — database is read-only at runtime

### Updating the Database

When new data is added or the booklet is updated:
1. Run extraction pipeline locally
2. Rebuild `sgma.db`
3. Redeploy to Railway (new Docker image with updated database)

## Currency and Maintenance

The SWRCB booklet covers law as of January 1, 2025. The Water Board publishes updated versions periodically. When an update is published or when specific legislative amendments are enacted:

1. For a new booklet: re-run the full extraction pipeline
2. For individual section amendments: manually update the relevant records in the database
3. For new case law: add to the `cases` table following the same extraction pattern

The 2025-2026 California legislative session has pending SGMA bills (AB-1413, AB-1466, SB-872) that may require updates if enacted.
