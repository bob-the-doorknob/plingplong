# Progress - 2026-11-21

- A: supplied archive and extracted starter match byte for byte. Read all starter
  runtime/scorer/build files. Direct baseline reproduced: 1210.470 s, zero misses.
  Official website refresh and Docker make sample blocked; A container gate open.
- B: 1..8 worker LPT candidates, millisecond scoring, stable tie handling and
  inventory validation implemented. Eight tests passed, including official sample.
  Tests observed failing before implementation (11 assertion failures with stub).
- C: deferred until pinned SQLGlot source and Stage A container verification exist.
- D: direct official scorer: 1104.510 s, zero misses, 4 workers vs starter's 3.
  Both select 1620 tests and 103.047 recorded seconds per commit. stdout 210840
  bytes optimized vs 259440 starter. Initial host CPU 0.015625 s optimized;
  rerun reports 0.0 s due to clock granularity. Wall ~0.0054 s. No server CPU claim.
- E: root Dockerfile and adjusted Makefile ready, .dockerignore limits build context.
  No successful Docker build/run. Pytest unavailable; install failed with WinError
  10013 on PyPI. unittest suite uses real scheduler and official scorer.

Blockers: outbound sockets denied; Docker engine pipe absent, Docker config access
is denied; make missing; WSL E_ACCESSDENIED. Git safe-directory check bypassed only
per command, but .git/config, FETCH_HEAD and index.lock writes remain denied.
Commit failed on index.lock; push failed because main has no commit. No SHA exists.
No permission escalation available in this session. Files preserved in workspace.

Immediate next action in a normal user terminal: restore network and Docker/WSL,
then configure origin and fetch before choosing a branch or committing:

    git remote add origin https://github.com/bob-the-doorknob/Buildathon.git
    git fetch origin
    git log --oneline --all --decorate -10

If origin already exists, inspect it rather than repeating add. Reconcile remote
history safely; never force-push. Install pytest, run tests and make sample before
commit/push. Fetch exact SQLGlot revision before indexing source. Public visibility
and general event license requirements still require checking before submission.

Final independent review: no concrete scheduler/scoring findings. Official
Makefile does not enforce the 180-second wall timeout; measure/enforce that
separately during Docker acceptance. Reviewer reran benchmark and regenerated
ignored output.jsonl; subsequent scorer validation remains valid.

## Phase 2 recovery and evidence

Fresh checks: process identity is CodexSandboxOffline. Git add fails creating
.git/index.lock. Docker now reports permission denied on docker_engine (rather
than the historical missing pipe); config.json also access denied. WSL remains
E_ACCESSDENIED. Make absent; pytest module absent. curl to GitHub fails immediately.
The session permission profile explicitly grants .git read access, not writes,
and disallows sandbox escalation. This is evidence of execution isolation;
there is no evidence of a stale Git lock, broken credentials or OneDrive locking.
No locks/security settings were changed. Repeating privileged operations here
will not recover those capabilities.

Manual recovery: use a normal user terminal or a Codex session with workspace
Git writes, outbound networking and Docker/WSL access. Confirm `git status`,
`git remote -v`, `docker info`, `wsl --status`, and availability of GNU Make.
Configure/fetch origin using the earlier commands, inspect remote history,
then run the README checks. Do not delete locks or force-push. Git authentication
has not been reached/tested. No commit SHA or push exists.

Fresh baseline: all 30 sample outputs accepted, starter 1210.470 s, optimized
1104.510 s, zero misses. First host CPU 0.015625 s each; ~0.0047 s wall optimized.

New code: impact.py + tests/test_impact.py. Red: four assertion failures for missing
narrowing with all-tests stub. Green: 20 total tests. File-level transitive import
selection tested only on synthetic source. Missing metadata retains all tests.
Pinned source fetch failed through shell networking and web raw-file lookup.
No source-specific relationships were invented, no production narrowing enabled.

Research reviewed: NameRTS abstract/repository (bipartite name reachability),
testmon (execution dependencies), pytest-depper (AST dependencies), pytest-impact
(fixtures), Coverage.py contexts. This implementation uses basic AST import
reachability only. Name-level pruning and coverage metadata were deferred, not
empirically rejected. Coverage collection needs the pinned checkout plus locked
organizer environment and per-test setup/fixture mapping; none were available.

Next: obtain pinned SQLGlot checkout, validate static graph completeness and
organizer test mapping. Inspect dynamic dialect registry directly. Measure
file-level/transitive candidates and independent mutations before enabling them.
Docker acceptance and public-repository/licensing checks remain outstanding.

Phase 2 final host measurements:

| Variant | Simulated seconds | Missed commits | Host CPU seconds | Tests/commit |
| --- | ---: | ---: | ---: | ---: |
| Original starter | 1210.470 | 0 | 0.015625 | 1620 |
| Existing optimized scheduler | 1104.510 | 0 | 0.000000 | 1620 |
| Experimental static, missing-index fallback | 1104.510 | 0 | 0.078125 | 1620 |
| Static with pinned source | unavailable | unknown | unknown | unknown |
| Coverage hybrid | not implemented | unknown | unknown | unknown |

Fallback measurement reparsed each patch and rescheduled each selection (0.0802 s
wall); production still computes its unchanged all-test schedule once. This is a
fallback validation, not evidence that dependency narrowing improves the target.
Final full suite: 20 tests passed. Official scorer rerun: 1104.510 s, zero misses.
No Docker execution, Git commit or push became possible during this phase.

References:
- https://arxiv.org/abs/2605.25356
- https://github.com/ZJU-CTAG/NameRTS
- https://www.testmon.org/
- https://github.com/ryx2/pytest-depper
- https://github.com/az-pz/pytest-impact
- https://coverage.readthedocs.io/en/latest/contexts.html

## Phase 3 checkpoint

P0: fresh 20-test suite passed before changes. Official host benchmark reproduced
1210.470 s starter, 1104.510 s LPT, zero misses; 0.015625 s CPU for each and
~0.0048 s optimized wall time. Read local SCORING.md; challenge refresh failed.
Git add still denied on index.lock; Docker pipe/config access denied; shell
networking denied. No escalation supported. No retries or security changes.

Research: successfully inspected README documentation for sophiayuanproj,
jklein07 and JuanQuenga. Other seven provided repositories inaccessible. Academic
abstract and general-tool documentation reviewed. Full comparison and URLs in
RESEARCH_COMPARISON.md. No competitor source code or maps copied.

Pinned SQLGlot tree fetch failed through web; shell GitHub connection failed.
No real target index or coverage generation/mutation labeling was possible.
Production hybrid activation gate remains unsatisfied.

Independent implementation: semantic.py and tests/test_semantic.py. Ten new
behavior tests cover function/method bodies, defaults/decorators, inheritance,
class attributes, imports/globals, added/removed/renamed definitions, duplicate
scopes, nested/conditional definitions, async functions and textual AST equality.
Red: seven assertion failures with stub; green: 30 total tests pass. New module
is experimental and excluded from Docker. Production selector hash unchanged:
83CB3073EDFF30E95DCF4DEFB2EA3AE8C997EAD3AB4E8912E8396741583BA21D.

Next action remains normal-user network/Git/Docker access (earlier recovery
commands), then obtain exact pinned checkout and collect independently verified
per-test execution + source/file-read attribution. No SHA or push exists. Public
visibility must be changed manually before submission; not changed by agent.

Final Phase 3 verification: python -m unittest discover -s tests -q -> 30 pass;
python benchmark.py -> starter 1210.470 s, LPT 1104.510 s, zero misses, 1620 tests
per commit. LPT host CPU 0.015625 s, wall 0.005713 s; host total 1104.525625 s
is not a server median or container CPU measurement. Official score.py rerun
accepted output at 1104.510 s and zero misses.
Synthetic locality throughput check (1000 same small source pairs, tracemalloc
on): CPU 0.78125 s, wall 0.80838 s, traced Python allocation peak 300722 bytes.
This does not measure target performance or process RSS. No target AST/coverage
ablation scores are reported because target evidence could not be obtained.

## Environment recovery / first container checkpoint - 2026-11-21

Historical restrictions above are resolved for this session: whoami -> Andrew;
safe.directory already includes repository; Git remote add/fetch succeeded; Docker
Engine 29.8.0 reports linux/x86_64; GitHub HTTP 200 and challenge download succeed.
.git still owned by CodexSandboxOffline, but current access works. No ownership,
ACL, firewall or security changes made. Origin correctly configured. Remote had
no refs (git fetch and git ls-remote succeeded with no remote commits).

Fresh 30-test suite passes; host benchmark reproduces 1210.470 s starter and
1104.510 s LPT, zero misses. Docker linux/amd64 build succeeds. Full official
runtime flags pass with host 180-second timeout: 30 JSON lines, 210840 bytes,
1104.510 simulated seconds, zero misses, 0.4128374 s Docker CLI wall time.
Container CPU not measured. Make unavailable, so equivalent commands executed
using Python subprocess for byte-exact stdout and timeout enforcement.

Downloaded and read current official track page. It requires a public repository
and commit, keeps submitted commits fetchable through final results, and reports
practice submissions limited to once an hour initially. No visibility change or
leaderboard submission yet. Production selector and scheduler unchanged.

Next: commit/push verified foundation, then submit exact hash once public access
and website authentication are available. Hybrid work stays deferred until this
first submission milestone is handled.
