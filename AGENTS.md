# Repository instructions

- Read blast-radius-sample/README.md and SCORING.md before changing scored behavior.
- Preserve the original starter and user files. Never encode sample failure labels.
- SQLGlot source must be eb11aec4be8cb2122afe713a4816662c3f0fb2fa.
- Standard library runtime; deterministic behavior; tests before nontrivial changes.
- Score integer milliseconds and 2 seconds per occupied worker, max eight workers.
- Unknown impact must conservatively select all tests. A sqlglot .py edit whose
  ast.dump is unchanged selects only its text readers (hits[path]) plus untraced
  tests, and never forces a full fallback of a multi-file patch. Shared readers,
  failed reconstruction or coding[:=] on lines 1-2 still select all tests. Any
  edit of an indexed SQL fixture, comments included, selects its observed readers;
  shared or missing readers select all tests.
- Phase 13 structure rules (non-core files unless noted): a function header edit
  with literal new defaults and unchanged decorators selects that code object's
  observations (core files too); an added, removed or redefined non-dunder method
  with literal defaults and pure decorators selects receivers of the class family
  and import-time holders, including ancestor reads of the name; a top-level
  literal or from-import rebinding selects bytecode readers, following importing
  modules one level; edits of non-collection test modules select their tests and
  importer files, or only edited test methods. Import-time or <module> reads,
  reflection, state writes, unobserved readers and class writes fall back.
- Class-level assignment values may narrow in a
  non-core file (not parser.py, generator.py, tokens.py, dialects/dialect.py,
  expressions/core.py or any __init__.py), using traced attribute reads. Import
  reads, class-body reads, runtime class writes and cache-changing readers widen
  to every test touching a holder class. Module reads or missing evidence select
  all tests, except reads of a proven unchanged Expr registry key for isolated
  boolean flag changes in a direct leaf Expression class. Literal assignments
  that change type or start evaluating an expression also fall back.
- One structural exception is an appended literal-return override of an already
  inherited SQL method in a direct leaf Generator. Follow exact receiver evidence,
  retain readers, importers and uncertain tests, and fall back on a related
  reflective import read, class write, subclass or missing evidence.
- Runtime: offline, read-only, nobody, HOME=/tmp, 64 MB tmp, 2 CPUs, 4 GB RAM,
  max 256 processes, 3 minute timeout (4.5 final), stdout <=2 MB.
- Build: 4 CPUs, 8 GB, 10 minutes; allowed registries/fixed releases/pinned SQLGlot
  only. Root Dockerfile; repository <=20 MB; no submodules or LFS.
- Verify: python -m unittest discover -s tests -v; python benchmark.py;
  python score.py blast-radius-sample/sample blast-radius-sample/sample/answers.json output.jsonl.
- With dependencies available: python -m pytest tests; make sample; make check.
- Host checks never prove Docker acceptance. Record exact blockers in PROGRESS.md.
- Read files once, search targeted sections, use one agent unless tasks are independent.
- Consult current library docs with ctx7 library then ctx7 docs when API-specific
  changes need documentation; never include secrets in queries.
- Never force-push, change visibility or submit without authorization.
- Production evidence must match the pinned archive and full organizer ID set.
  Rebuild with the README commands and run tools/check_mutations.py after both mutation runs.
- Structural metadata must match the pinned catalog and base evidence digest.
  Keep scalar fallbacks for aliases, captures and unobserved readers.
  Test-side narrowing requires the terminal literal and two-order operand
  evidence. Retain raw readers and uncertain tests. Re-run validation and
  the frozen holdout before changing either rule.
