# Repository instructions

- Read blast-radius-sample/README.md and SCORING.md before changing scored behavior.
- Preserve the original starter and user files. Never encode sample failure labels.
- SQLGlot source must be eb11aec4be8cb2122afe713a4816662c3f0fb2fa.
- Standard library runtime; deterministic behavior; tests before nontrivial changes.
- Score integer milliseconds and 2 seconds per occupied worker, max eight workers.
- Unknown impact and comment-only changes must conservatively select all tests.
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
- impact.py is experimental, fixture-tested only. Do not enable production
  narrowing without pinned-source, organizer-ID and mutation/sample validation.
