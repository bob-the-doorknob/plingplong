# Architecture

selector.py loads /data/tests.json, validates test identifiers and durations,
then schedules every numbered test. Patches supply commit identifiers only.
No sample answer, patch signature, edit category or network is used at runtime.

schedule(tests) sorts by descending integer milliseconds, then test number.
For each count from 1 through min(8, selected count), assign the next test to
the least-loaded worker, breaking load ties by worker index. Drop empty workers.
Compare maximum load + 2000 ms per occupied worker. First minimum wins, favoring
fewer workers on equal costs. Empty inventory returns []. Rounding matches the
official scorer: floor(seconds * 1000 + 0.5).

Runtime is O(8 * 8 * tests + tests log tests), computed once per batch. No writes
are required. Diagnostics go to stderr; stdout contains only compact JSON lines.
Missing or malformed inventory fails before any answers are emitted.

score.py is the unchanged official scorer. benchmark.py measures both selectors
on the host; only this development tool reads sample answers. Root Makefile
runs the official container restrictions against the preserved sample directory.

Static dependency analysis is deliberately deferred: pinned source could not be
fetched and Docker baseline is blocked. Current conservative fallback is all tests
for every patch, including comments, fixtures, renames and unfamiliar file types.
LPT optimizes among eight heuristic schedules, not every possible partition.

## Phase 2: experimental static index

impact.py is a development-only candidate, excluded from the Docker image.
`build_index(Path(checkout))` parses sqlglot/ and tests/ Python files without
executing source. It returns file-to-module names, deterministic reverse import
edges and a completeness flag. Relative imports and package initialization edges
are included. `select_tests(diff, tests, index)` returns actual organizer numbers
for transitively affected test files, or all numbers on uncertainty.

Ordinary same-path Git text diffs have their hunk counts validated. Renames,
add/delete files, quoted paths, binary changes, malformed hunks, unknown files,
comment-only patches, core infrastructure, dialect files, package initialization
and shared test/config changes retain all tests. Unresolved imports, syntax
errors and detected dynamic imports/reflection invalidate the entire index.
An empty candidate set also retains all tests.

This is import reachability, not NameRTS name-level analysis or a safety proof.
Alias calls, callbacks, resources, monkeypatching and implicit Python behavior
are not fully modeled. Do not enable it in selector.py until a verified pinned
checkout, complete organizer test mapping and differential mutation/sample
validation support it. Current dynamic guard may prevent all SQLGlot narrowing;
that is an intentional safety outcome, not measured competitive improvement.
No target index has been generated; no third-party source was copied.

## Phase 3: semantic locality component

semantic.py independently implements classify_change(old, new). It parses both
texts without importing/executing them. Function/method bodies are compared by
qualified name, while a separate skeleton retains defaults, annotations,
decorators, class bases/keywords/attributes, import statements and module code.
Body-only edits identify candidate scopes. Structural edits, added/removed scopes,
invalid syntax and duplicate scopes require broad analysis. Nested functions stay
inside the outer function's body; control-flow definitions stay in module scope.

text_changed is separate from ast_equal. AST equality never means safe to skip:
source readers, tracebacks, line inspection and fixture processing can observe
text. The classifier supplies locality evidence only; it does not claim semantic
program equivalence or decide test exclusion. It remains outside the Docker
payload with impact.py. Production selector.py and scheduler are unchanged.

Coverage collection and hybrid composition are blocked by unavailable pinned
source and organizer execution environment. No fabricated completeness flag or
empty coverage map is used to enable narrowing. See RESEARCH_COMPARISON.md for
the conceptual design, evidence status and deferred techniques.
