# Odin Coding Standards

## Core Expectations

- Write production-quality, strongly typed code.
- Preserve existing architecture and public behavior.
- Prefer focused, incremental changes over broad rewrites.
- Keep modules cohesive and dependencies one-directional.
- Add or update tests whenever behavior changes.
- Update documentation when contracts or architecture change.

## Design

- Use dependency injection for external services and infrastructure.
- Prefer composition over inheritance.
- Use dataclasses or equivalent value objects when they clarify data contracts.
- Define typed interfaces at architectural boundaries.
- Keep services small and centered on one responsibility.
- Reuse existing abstractions before adding new ones.

Avoid:

- God classes and large methods
- Circular dependencies
- Hidden global state
- Tight coupling to frameworks or vendors
- Duplicate orchestration paths
- Unexplained breaking changes

## Python

- Follow the project’s configured formatter, linter, and type-checker.
- Add type annotations to public APIs and new application logic.
- Keep FastAPI transport concerns at the API boundary.
- Inject persistence, Git, filesystem, and model-provider dependencies.
- Raise or map domain-specific errors deliberately; do not silently swallow failures.
- Use async code only where the operation is genuinely asynchronous.

## TypeScript and React

- Keep TypeScript strict and avoid `any` unless a boundary requires it and the reason is documented.
- Separate UI components from API access and domain state.
- Prefer small, composable components and explicit props.
- Preserve accessibility, loading, empty, and error states.
- Use the repository’s configured linting and formatting rules.

## Tests

- Cover the behavior being added or changed.
- Prefer deterministic unit tests for domain and application services.
- Add integration tests at important infrastructure and API boundaries.
- Test failure, retry, authorization, approval, and recovery paths where relevant.
- Do not commit knowingly failing tests.

## Documentation

- Keep architectural decisions and user-visible behavior current.
- Explain non-obvious tradeoffs close to the relevant code or in `docs/`.
- Avoid comments that merely restate the code.

## Git Hygiene

- Work on a branch; do not push directly to `main`.
- Keep commits focused and descriptive.
- Exclude secrets, credentials, generated caches, and local environment data.
- Review the diff and run relevant validation before committing.

## Definition of Done

A change is complete when it is production-ready, tested, documented, backwards-compatible where required, architecturally consistent, and represented by safe Git history.
