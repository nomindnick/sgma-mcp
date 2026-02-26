# SGMA MCP Server — Implementation Plan

## How This Plan Works

This project is implemented in phases. Each phase contains sprints that can be completed independently in roughly one hour or less. Complete one sprint at a time by prompting Claude Code (e.g., "Plan and implement Sprint 2.1").

After extraction pipeline sprints (Phase 2), Claude Code should spawn a verification subagent to validate the output before moving to the next sprint. Human review is available as a second pass but is not the bottleneck.

After Phase 3, the database is populated and queryable. After Phase 4, the MCP server is functional. After Phase 5, it's deployed and usable.

---

## Phase 1: Project Setup

### Sprint 1.1 — Project Scaffolding ✅

**Goal:** Set up the Python project with all dependencies and directory structure.

**Tasks:**
- Initialize Python project with `pyproject.toml` (use `uv` for package management if available, otherwise standard pip)
- Create directory structure per SPEC.md (`src/sgma_mcp/`, `scripts/`, `data/extracted/`, `tests/`)
- Add dependencies:
  - `mcp` — MCP Python SDK
  - `openai` — for embeddings
  - `anthropic` — for Claude API enrichment pipeline
  - `sqlite-vec` — vector similarity in SQLite
  - `pdftotext` system dependency (or `pymupdf` as Python alternative)
- Create `src/sgma_mcp/__init__.py`
- Create database schema script (`scripts/create_schema.py`) implementing the full schema from SPEC.md (all tables including future-use tables like `evaluations`, `agency_documents`)
- Create a `config.py` with settings: database path, embedding model name, embedding dimensions, chunk size thresholds
- Verify setup: run schema creation, confirm empty database is created at `data/sgma.db`

**Output:** A working Python project that creates a properly-schemaed empty database.

---

## Phase 2: Data Extraction Pipeline

### Sprint 2.1 — Raw Extraction and Segmentation

**Goal:** Extract raw text from the PDF and segment it by content type using known page boundaries.

**Tasks:**
- Write `scripts/extract_raw.py`:
  - Extract full text from PDF using `pdftotext -layout` (subprocess call) or `pymupdf`
  - Save to `data/extracted/raw_text.txt`
- Write `scripts/segment.py`:
  - Define content type segments with page boundaries (derived from the TOC):
    - `explanatory`: pages 1-5 (intro, history, common law, Winters doctrine)
    - `cases`: page 6 (recent judicial decisions)
    - `findings`: pages 7-9 (uncodified legislative findings)
    - `gov_code_sections`: pages 10-15
    - `water_code_related_sections`: pages 16-28
    - `water_code_sgma_sections`: pages 29-99
    - `ccr_dwr_sections`: pages 100-158
    - `ccr_swrcb_sections`: pages 159-167
    - `ccp_sections`: pages 168-198
    - `leg_history`: pages 199-203
  - Extract each segment from the raw text (using page markers or character offsets)
  - Save to `data/extracted/segments.json` with structure: `[{type, page_range, text}]`
- **Verification (subagent):**
  - Total page coverage accounts for all pages in the PDF (no gaps)
  - Each segment's text starts and ends with expected content (spot-check first/last lines)
  - No segment is empty

**Output:** `data/extracted/raw_text.txt` and `data/extracted/segments.json`

**Note:** The page boundaries listed above are approximate based on the TOC. The actual implementation should verify boundaries by looking for the section header markers in the text (e.g., "SGMA STATUTE – WATER CODE", "SGMA REGULATIONS – CODE OF REGULATIONS TITLE 23", "GROUNDWATER ADJUDICATIONS – CODE OF CIVIL PROCEDURE", etc.). Adjust as needed during implementation.

### Sprint 2.2 — Section Parsing

**Goal:** Parse statute and regulation segments into individual section records.

**Tasks:**
- Write `scripts/parse_sections.py`:
  - Input: the section-type segments from `segments.json` (gov_code, water_code_related, water_code_sgma, ccr_dwr, ccr_swrcb, ccp)
  - Split each segment into individual sections using the `§ XXXXX.` boundary pattern
  - For each section extract:
    - `section_number` — the number after `§` (e.g., "10727.2", "354.28")
    - `title` — the bracketed title (e.g., "[Required Plan Elements]")
    - `full_text` — everything from the section header to the next section boundary
    - `amendment_history` — the parenthetical at the end (e.g., "(Added by Stats. 2014, Ch. 346...)")
    - `code` — derived from which segment it came from (water_code, gov_code, ccr_title_23, ccp)
    - `content_type` — statute or regulation
  - Handle edge cases:
    - Sections that span page breaks (page headers/footers in the middle of text)
    - The `***` markers that indicate omitted sections
    - Hierarchy headers (Division, Part, Chapter, Article headings) that appear between sections — capture these for hierarchy_path but don't create section records for them
  - Save to `data/extracted/sections.json` with structure: `[{code, section_number, title, full_text, amendment_history, content_type, hierarchy_context}]`
    - `hierarchy_context` is the raw hierarchy headers seen before this section — enrichment in Sprint 2.4 will clean this into a proper path
- **Verification (subagent):**
  - Section count is reasonable (expect ~150-200 sections total across all codes)
  - No duplicate section numbers within the same code
  - Every section has non-empty section_number, full_text
  - Section numbers match expected patterns per code (Water Code: 3-5 digit numbers; CCR: 3-digit numbers in 350-358 range and 1030-1046 range; CCP: 3-digit numbers in 830-852 range)
  - Spot-check 5-10 random sections: compare parsed text against the corresponding segment text to verify no truncation or merging
  - Check that amendment history was correctly separated from body text

**Output:** `data/extracted/sections.json`

### Sprint 2.3 — Supplementary Content Parsing

**Goal:** Parse the non-section content: case citations, explanatory text, uncodified findings, and legislative history.

**Tasks:**
- Write `scripts/parse_supplementary.py` (or separate scripts per type):
  - **Cases** (from the `cases` segment):
    - Parse each bullet point into a case record
    - Extract: case_name, citation, year, court (inferred from citation format), summary/holding
    - Also scan the explanatory text segments for additional case citations (Katz v. Walkinshaw, Hudson v. Dailey, City of Pasadena v. City of Alhambra, City of Los Angeles v. City of San Fernando, City of Barstow v. Mojave Water Agency, Tehachapi-Cummings, City of Santa Maria v. Adam, Agua Caliente v. Coachella Valley)
    - Save to `data/extracted/cases.json`
  - **Explanatory text** (from the `explanatory` segment):
    - Split into logical sections by headers ("A Brief History of SGMA", "The Common Law of Groundwater", "The Winters Doctrine...")
    - Save to `data/extracted/explanatory.json` with structure: `[{title, text}]`
  - **Uncodified findings** (from the `findings` segment):
    - Parse the numbered findings: (a)(1) through (a)(13) and (b)
    - Save to `data/extracted/findings.json`
  - **Legislative history** (from the `leg_history` segment):
    - Parse each entry: bill_number, author, chapter, year
    - Save to `data/extracted/leg_history.json`
- **Verification (subagent):**
  - Cases: expect ~4 cases from the Recent Judicial Decisions page + ~8 cases from explanatory text. Each has name, citation, and summary.
  - Explanatory: 3 sections with non-empty text
  - Findings: numbered items (1) through at least (13) are present
  - Legislative history: entries from 2014 through 2024, with bill numbers matching expected format (AB/SB + number)

**Output:** `data/extracted/cases.json`, `data/extracted/explanatory.json`, `data/extracted/findings.json`, `data/extracted/leg_history.json`

### Sprint 2.4 — Claude API Enrichment

**Goal:** Use the Claude API to enrich parsed sections with structured metadata: clean hierarchy paths, cross-references, subdivision boundaries, and defined terms.

**Tasks:**
- Write `scripts/enrich_sections.py`:
  - Read `data/extracted/sections.json`
  - For each section (or in batches for efficiency), call the Claude API to extract:
    - `hierarchy_path` — clean, normalized path (e.g., "Div 6 / Part 2.74 / Ch 6 / Art 1") derived from the `hierarchy_context` captured in Sprint 2.2
    - `cross_references` — list of other section numbers referenced in the text (e.g., "Section 10727" → cross-ref to water_code § 10727), with the referencing code identified
    - `subdivision_boundaries` — for long sections, the character offsets or text markers for major subdivisions (a), (b), (c) etc., to enable subdivision-level chunking later
    - `defined_terms_used` — any SGMA defined terms (from § 10721 or § 351) that appear in the section
  - Use a structured output prompt that returns JSON. Include a few manually-crafted examples in the prompt for consistency.
  - Merge enrichment data back into the section records
  - Save to `data/extracted/structured_sections.json`
  - Log API usage (tokens, cost estimate) for transparency
- **Verification (subagent):**
  - All original section fields are preserved (enrichment didn't clobber core data)
  - Hierarchy paths are well-formed and consistent within each code
  - All Water Code SGMA sections have hierarchy paths starting with "Div 6 / Part 2.74"
  - All CCR sections have paths starting with appropriate division/chapter
  - Cross-references point to section numbers that exist in the dataset (cross-check against the full section list)
  - Subdivision boundaries, where present, have valid structure
  - Spot-check 5-10 sections for cross-reference accuracy

**Output:** `data/extracted/structured_sections.json`

**Note:** This sprint involves Claude API calls that cost money (~$2-5 estimated for the full corpus). Ensure ANTHROPIC_API_KEY is configured before running.

---

## Phase 3: Database Population

### Sprint 3.1 — Load Data into SQLite

**Goal:** Populate the SQLite database from all extracted JSON artifacts.

**Tasks:**
- Write `scripts/load_database.py`:
  - Load `structured_sections.json` → `sections` table
  - Load `cases.json` → `cases` table
  - Load `explanatory.json`, `findings.json`, `leg_history.json` → `auxiliary_content` table
  - Extract definitions: parse § 10721 (Water Code definitions) and § 351 (CCR definitions) from the sections data, split individual defined terms into `definitions` table records with FK to the source section
  - Load cross-references from the enrichment data → `cross_references` table
  - Build the FTS5 index:
    - Create `chunks` records for all content (section-level chunks initially — subdivision chunking happens in Sprint 3.2 alongside embeddings)
    - Populate `chunks_fts` virtual table
  - Print summary statistics: row counts per table
- Run the script, verify database is populated
- **Verification (subagent):**
  - Row counts in `sections` table match count in `structured_sections.json`
  - Row counts in `cases`, `auxiliary_content`, `definitions`, `cross_references` are non-zero and match source JSON counts
  - FTS5 index returns results for known terms (e.g., "sustainable management criteria", "groundwater sustainability plan", "minimum threshold")
  - Sample SQL queries return expected results:
    - `SELECT * FROM sections WHERE code='water_code' AND section_number='10727.2'` returns the correct section
    - `SELECT * FROM definitions WHERE term LIKE '%basin%'` returns the § 10721 definition
    - `SELECT * FROM cross_references LIMIT 10` shows properly formed relationships

**Output:** Populated `data/sgma.db` with all tables except embeddings.

### Sprint 3.2 — Embeddings and Subdivision Chunking

**Goal:** Generate embeddings for all content, with subdivision-level chunking for long sections.

**Tasks:**
- Write `scripts/generate_embeddings.py`:
  - Read all sections from the database
  - For each section:
    - If full_text <= ~500 tokens: create one chunk (chunk_index=0) with the full text
    - If full_text > ~500 tokens: create chunk_index=0 with full text AND additional chunks for each major subdivision identified in the enrichment data (Sprint 2.4 subdivision_boundaries)
    - Set `chunk_heading` to the subdivision label (e.g., "(a)", "(b)(1)") for subdivision chunks
  - Also create chunks for: case summaries, explanatory text sections, uncodified findings
  - Call OpenAI API to generate embeddings (text-embedding-3-small, 1536 dimensions) for each chunk
  - Store embeddings in the `chunks` table `embedding` column using sqlite-vec format
  - Update `chunks_fts` to include all new chunks
  - Register the sqlite-vec virtual table for similarity search
  - Print statistics: total chunks, chunks per source type, embedding dimensions confirmed
- **Verification (subagent):**
  - No NULL embeddings in the chunks table
  - Embedding dimensions are uniformly 1536
  - Total chunk count is reasonable (expect 300-600 total)
  - Long sections (e.g., § 10727.2, § 354.28) have multiple chunks
  - Short sections have exactly one chunk
  - Quick similarity search test: embed a test query and retrieve top-5 results, verify they're topically relevant

**Output:** `data/sgma.db` now fully populated with embeddings.

**Note:** This sprint requires OPENAI_API_KEY. Cost is minimal (~$0.01-0.05 for this corpus size).

### Sprint 3.3 — Database Validation and Query Testing

**Goal:** Build validation tooling and run comprehensive tests against the populated database.

**Tasks:**
- Write `scripts/validate.py` as a CLI tool that runs a suite of checks:
  - **Integrity checks:**
    - All FKs in `definitions.source_section_id` point to existing sections
    - All `cross_references` from_id/to_id pairs point to existing records of the declared type
    - No orphaned chunks (every chunk's source_id exists in the referenced source table)
  - **Completeness checks:**
    - All codes have sections: water_code, gov_code, ccr_title_23, ccp
    - Definitions exist for key terms: "basin", "groundwater sustainability agency", "sustainable yield", "undesirable result"
    - Cross-references exist between statutes and regulations
  - **Search quality checks (golden queries):**
    - Citation lookup: `water_code 10727.2` → returns "Required Plan Elements"
    - Keyword search: "minimum threshold" → returns § 354.28 and § 10727.2 in top results
    - Semantic search: "what fees can a GSA charge" → returns §§ 10730, 10730.1, 10730.2 in top results
    - Definition lookup: "basin" → returns definition from § 10721
    - Cross-reference: § 354.28 → shows relationship to § 10727.2
  - Print pass/fail for each check with details on failures
- Run the validation suite, fix any issues discovered
- Reusable: this script will be run again when new data sources are added

**Output:** Validation passes. Database is ready to be served.

---

## Phase 4: MCP Server

### Sprint 4.1 — Server Scaffolding and Lookup Tool

**Goal:** Create a working MCP server with the `lookup_section` tool.

**Tasks:**
- Write `src/sgma_mcp/db.py`:
  - Database connection management (open SQLite, load sqlite-vec extension)
  - `get_section(code, section_number)` → returns section record or None
  - Basic query helpers
- Write `src/sgma_mcp/server.py`:
  - MCP server initialization using the `mcp` Python SDK
  - Register `lookup_section` tool:
    - Parameters: `code` (enum: water_code, gov_code, ccr_title_23, ccp), `section_number` (string)
    - Returns: formatted section text with title, hierarchy path, amendment history, and full text
    - Clear tool description that tells Claude when/how to use it
  - Support both stdio transport (for local testing) and SSE transport (for deployment)
- Test locally: run server in stdio mode, verify `lookup_section` returns correct results for a few known sections
- Write a basic test in `tests/` that starts the server and calls the lookup tool

**Output:** A working MCP server with one tool. Can connect via Claude Code for local testing.

### Sprint 4.2 — Hybrid Search Tool

**Goal:** Implement the `search` tool with combined FTS5 and embedding retrieval.

**Tasks:**
- Write `src/sgma_mcp/search.py`:
  - `keyword_search(query, source_types, limit)` → FTS5 query on `chunks_fts`, returns ranked results with BM25 scores
  - `semantic_search(query, source_types, limit)` → embed query via OpenAI API, vector similarity via sqlite-vec, returns ranked results with similarity scores
  - `hybrid_search(query, source_types, limit)` → runs both, merges results:
    - Normalize scores to 0-1 range
    - Deduplicate by source record (same section shouldn't appear twice)
    - Combine scores with configurable weighting (default: 0.4 keyword + 0.6 semantic, tunable)
    - Return top-N results sorted by combined score
  - Citation detection: regex check for `§ XXXXX` patterns in query → redirect to direct lookup
  - Result formatting: each result includes source_type, code/section_number or title, text snippet (first ~200 chars or matched chunk), relevance score
- Register `search` tool in `server.py`:
  - Parameters: `query` (string), `source_types` (optional list of strings), `limit` (optional int, default 10)
  - Clear tool description explaining hybrid search behavior and available source type filters
- Test: run golden queries from Sprint 3.3 through the MCP tool interface, verify quality

**Output:** Working search tool added to the MCP server.

### Sprint 4.3 — Remaining Tools

**Goal:** Implement `get_definition`, `get_related`, and `list_structure` tools.

**Tasks:**
- Add to `src/sgma_mcp/db.py`:
  - `get_definitions(term)` → fuzzy match on `definitions.term`, return all matches with source section info
  - `get_related(code, section_number)` → query `cross_references` for the section, join to source tables for context
  - `get_structure(code, chapter)` → query `sections` for hierarchy, group by hierarchy_path components
- Write `src/sgma_mcp/tools/definitions.py`:
  - `get_definition` tool: look up term, return definition text + source citation
  - Handle partial matches (e.g., "GSA" should match "groundwater sustainability agency")
- Write `src/sgma_mcp/tools/related.py`:
  - `get_related` tool: return related provisions grouped by relationship type
  - Format: "Implementing regulations: [list], Interpreting cases: [list], See also: [list]"
- Write `src/sgma_mcp/tools/structure.py`:
  - `list_structure` tool: return hierarchical outline
  - When called with no args: return top-level structure (available codes and their major divisions)
  - With code: return chapters/articles
  - With code + chapter: return sections with numbers and titles
- Register all tools in `server.py` with clear descriptions
- Integration test: connect via Claude Code locally, run through a realistic research workflow:
  - "What are the required plan elements for a GSP?" → should use search + lookup
  - "What does 'undesirable result' mean under SGMA?" → should use get_definition
  - "What regulations implement the plan content requirements?" → should use get_related
  - "Give me an overview of the SGMA statute structure" → should use list_structure

**Output:** Full MCP server with all 5 tools functional.

---

## Phase 5: Deployment

### Sprint 5.1 — Railway Configuration

**Goal:** Configure the project for Railway deployment with HTTP+SSE transport.

**Tasks:**
- Create `Dockerfile`:
  - Python base image
  - Install system dependencies (any needed for sqlite-vec)
  - Copy `src/`, `data/sgma.db`, and `pyproject.toml`
  - Set entry point to run the MCP server with SSE transport
- Create `railway.toml` (or `railway.json`) if needed for Railway-specific config
- Configure environment variables:
  - `OPENAI_API_KEY` — needed for embedding queries at search time
  - `MCP_TRANSPORT` — set to `sse` for Railway
  - `PORT` — Railway provides this
- Ensure the server binds to `0.0.0.0:$PORT` when using SSE transport
- Test Docker build locally: `docker build` and `docker run`, verify MCP server responds
- Deploy to Railway:
  - Connect repository or push Docker image
  - Set environment variables
  - Verify deployment is running

**Output:** MCP server deployed and accessible on Railway.

### Sprint 5.2 — End-to-End Testing and Claude Configuration

**Goal:** Connect Claude to the deployed server and validate the full workflow.

**Tasks:**
- Configure Claude Code to use the Railway-deployed MCP server (add to MCP settings with the Railway URL)
- Run end-to-end research scenarios:
  - "Can my GSA impose fees on de minimis extractors?" → should pull § 10730, § 10721 definition, and the Mojave Pistachios case
  - "What are the monitoring network requirements for a GSP?" → should find § 10727.2 and § 354.34
  - "What is the timeline for DWR to review our GSP?" → should find § 10733.4
  - "What happens if DWR finds our plan inadequate?" → should trace through § 10733.6, § 10735, state intervention provisions
  - "Explain the common law of groundwater rights in California" → should pull explanatory text and key cases
- Verify response quality: Claude correctly cites sections, quotes text accurately, follows cross-references
- Tune tool descriptions if Claude isn't selecting the right tools for queries
- Document the Railway URL and MCP configuration for ongoing use

**Output:** Fully deployed and validated SGMA MCP server.

---

## Future Work (not yet planned as sprints)

### Adding Full Case Texts
- Source full opinions (manual export from Westlaw/Lexis or public court websites)
- Write extraction script per source format
- Load into `cases.full_text`, generate chunks and embeddings
- Add `lookup_case` MCP tool

### Adding DWR Guidance Documents
- Download DWR BMPs from water.ca.gov
- Extract and chunk
- Load into `guidance_documents` table

### Adding DWR GSP Evaluations
- Download evaluation staff reports from SGMA portal
- Parse per-element findings
- Load into `evaluations` table
- Add `search_evaluations` MCP tool with structured filters

### Adding Agency Documents
- Load GSA-specific GSP, MOUs, board resolutions
- Load into `agency_documents` table
- Add `search_agency_docs` MCP tool

### Automated Update Pipeline
- Monitor for new SWRCB booklet publications
- Diff-based update: compare new extraction against existing database, update changed sections
- Track legislative session for SGMA amendments
