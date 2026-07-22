# Repository Intelligence

Odin's repository intelligence extends the existing repository scan pipeline instead of introducing a second planner, runtime, tool platform, or embeddings stack.

## Architecture

- `backend/app/services/repository_intelligence.py` persists repository scan state, incremental file metadata, symbols, references, documentation records, dependency edges, and indexed revision metadata.
- `backend/app/services/repository_context.py` is the single reusable context service for planner and native chat.
- `backend/app/services/repository_graph.py` keeps impact and dependency queries behind a service abstraction so storage can evolve later.
- `backend/app/api/repositories.py` exposes repository lifecycle, search, context, references, file browsing, documentation, and impact APIs.

## Indexing lifecycle

1. Connect a repository with a validated local path.
2. Start indexing with `POST /api/repositories/{owner}/{name}/index` or run an immediate scan with `POST /api/repositories/{owner}/{name}/scan`.
3. The scanner records the indexed revision, compares current file hashes against the prior payload, and only reparses changed files.
4. Deleted files are removed from symbols, docs, references, and dependency edges during the rebuild.
5. Cancellation requests flip scan state to `cancelled` and are honored between file batches.

## Parser extension interface

- Python uses `ast` for symbols, imports, docstrings, and references.
- Script languages use the existing language-aware extractor hooks plus safe text fallback helpers for comments and references.
- Additional parsers should extend `_analyze_file` and return `AnalysisResult` values with symbols, imports, references, documentation, and architecture matches.

## Repository graph

Dependency and impact queries are exposed through `RepositoryGraphService`:

- dependencies of a file
- dependents of a file
- likely related tests
- symbol references

## Context retrieval

`RepositoryContextService` produces bounded context packages with:

- relevant files
- relevant symbols
- dependency relationships
- documentation
- tests
- repository summary
- indexed revision and stale-index notes
- token estimates

## Chat and planner integration

- Planner metadata now includes the repository context package, affected symbols, dependency relationships, likely tests, and uncertainty notes.
- Native chat accepts an attached repository and injects the same rendered repository context package into the LLM prompt before generation.

## Tool platform integration

Repository intelligence continues to rely on the existing repository and tool platform primitives for file discovery, path safety, and execution boundaries. Search and browsing APIs build on persisted scan payloads rather than bypassing workspace protections.

## Security model

- Local paths must be absolute, inside allowed scan roots, and pass `safe_child` validation.
- File browsing uses normalized relative paths.
- Large, ignored, and binary files are skipped by the repository indexer.
- Repository content is treated as untrusted input; documentation and code excerpts are stored as plain text only.

## API surface

- `POST /api/repositories/{owner}/{name}/index`
- `POST /api/repositories/{owner}/{name}/cancel-indexing`
- `POST /api/repositories/{owner}/{name}/reindex`
- `GET /api/repositories/{owner}/{name}/search`
- `GET /api/repositories/{owner}/{name}/context`
- `GET /api/repositories/{owner}/{name}/references`
- `GET /api/repositories/{owner}/{name}/documentation`
- `GET /api/repositories/{owner}/{name}/files`
- `GET /api/repositories/{owner}/{name}/impact`

## Adding a new language parser

1. Detect the file type in `_analyze_file`.
2. Implement a parser that emits `AnalysisResult`.
3. Populate symbols, imports, references, and documentation records.
4. Add representative fixture coverage in repository intelligence tests.
