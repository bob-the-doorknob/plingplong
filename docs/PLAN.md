# Foundation implementation plan

Goal: preserve the starter and improve scheduling without changing selection safety.
Spec: supplied task and blast-radius-sample/README.md and SCORING.md.
Architecture: retain the official selector/scorer, evaluate integer-millisecond LPT schedules for 1..8 workers.
Constraints: pinned SQLGlot eb11aec4be8cb2122afe713a4816662c3f0fb2fa; offline runtime; eight workers maximum; no answer-derived selection.
Review focus: empty inputs, equal durations, rounding, malformed inventory, stdout validity.

- [ ] Verify archive against extracted files; record direct baseline using official scorer.
- [ ] Preserve baseline Git milestone, without reconciling inaccessible remote history.
- [ ] Write scheduler and validation tests; observe failure, implement, run suite.
- [ ] Benchmark unchanged starter and optimized scheduler with official scorer.
- [ ] Document measured results and container/network blockers; commit locally and attempt push.
- [ ] Once Docker and network work, run make sample before static selection. Fetch pinned source before dependency indexing.

Files: selector.py (runtime), tests/test_selector.py (behavior), benchmark.py (local measurements), root Dockerfile/Makefile (official packaging), README.md and docs (evidence).
Execution: single agent, as explicitly requested. No worktree: empty repository initialized in designated workspace. No approval pause: user explicitly authorized execution.

## Phase 2 checklist
- [x] Reproduce scheduler and diagnose current environment restrictions.
- [ ] Add fixture-tested AST import/reverse-dependency index and strict diff handling.
- [ ] Keep narrowing experimental until pinned-source/sample validation is possible.
- [ ] Verify full suite and current scorer; document research and recovery steps.

## Phase 3 checklist
- [x] Reproduce known-good scheduler; verify source hash unchanged.
- [x] Research readable competitor documentation and primary references; record access gaps.
- [x] Implement AST locality with failing tests, then full-suite verification.
- [ ] Validate pinned SQLGlot import graph and collect coverage (source access blocked).
- [ ] Integrate and benchmark real hybrid (activation evidence unavailable).
- [ ] Docker acceptance, commit and push (execution isolation).
