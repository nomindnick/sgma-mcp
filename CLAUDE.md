# SGMA MCP Server

An MCP server providing authoritative, searchable access to California's Sustainable Groundwater Management Act (SGMA) legal corpus — statutes, regulations, case law, and related legal resources.

## Purpose

Built for a California public agency attorney doing SGMA work for a GSA client. The server gives Claude grounded access to exact statutory/regulatory text, enabling legally accurate research and work product with proper citations.

## Tech Stack

- **Language:** Python
- **Database:** SQLite + FTS5 (full-text search) + sqlite-vec (embeddings)
- **Embeddings:** OpenAI text-embedding-3-small
- **MCP Framework:** `mcp` Python SDK
- **Deployment:** Railway (HTTP+SSE transport)

## Project Structure

```
sgma-mcp/
├── CLAUDE.md                      # This file - project overview
├── SPEC.md                        # Detailed project specification
├── IMPLEMENTATION_PLAN.md         # Phased sprint plan
├── pyproject.toml
├── Dockerfile
├── src/
│   └── sgma_mcp/
│       ├── server.py              # MCP server entry point
│       ├── db.py                  # Database access layer
│       ├── search.py              # Hybrid search logic (FTS5 + embeddings)
│       └── tools/                 # MCP tool implementations
│           ├── lookup.py
│           ├── search.py
│           ├── definitions.py
│           ├── related.py
│           └── structure.py
├── scripts/                       # Data extraction pipeline
│   ├── extract_raw.py
│   ├── segment.py
│   ├── parse_sections.py
│   ├── parse_supplementary.py
│   ├── enrich_sections.py
│   ├── load_database.py
│   ├── generate_embeddings.py
│   └── validate.py
├── data/
│   ├── source-material/           # Original PDFs
│   ├── extracted/                 # Pipeline checkpoint artifacts
│   └── sgma.db                    # Final SQLite database
└── tests/
```

## Key Design Decisions

- **PDF is the primary data source.** The SWRCB SGMA Booklet (Jan 2025) contains statutes, regulations, case citations, explanatory text, and legislative history. Leginfo blocks crawlers (robots.txt `Disallow: /`), so the booklet serves as the authoritative compilation.
- **Checkpointed extraction pipeline.** Each pipeline step produces a reviewable JSON artifact. Fix upstream issues and re-run without redoing the whole pipeline.
- **Hybrid search.** Citation lookup (exact SQL match) + FTS5 keyword search + embedding similarity search. Different retrieval mechanisms for different query types.
- **Two-level chunking.** Section-level embeddings for all sections. Subdivision-level embeddings for long sections (500+ tokens) to preserve retrieval precision.
- **Database ships with deployment.** SQLite file is bundled into the Docker image. No separate database service needed.

## Data Model

Core tables: `sections` (statutes + regulations), `cases`, `definitions`, `cross_references`, `guidance_documents`, `evaluations`, `agency_documents`, `chunks` (unified embedding/search table).

See SPEC.md for full schema.

## Adding New Data Sources

Follow the extraction pipeline pattern: write source-specific extraction script → produce JSON checkpoint → load into database → generate embeddings for new chunks → redeploy.
