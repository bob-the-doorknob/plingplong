# Regression-selection research comparison

## Evidence and access (2026-11-21)

Research only; no competing code, generated maps, fixtures or answer tables were copied.
README claims were inspected, not reproduced. Scores do not identify feature contributions.
The challenge website and exact SQLGlot tree could not be fetched; local official
SCORING.md remains the available scoring authority. No updated rules are claimed.

Actually inspected competitor README documentation:
- [sophiayuanproj](https://github.com/sophiayuanproj/RWX---Blast-Radius): bytecode comparison, state fingerprints, attribute/file-read attribution, forward/reverse tracing, process-pool substitution and budgeted candidate execution. Interesting evidence collection; execution substitution needs equivalence checks.
- [jklein07](https://github.com/jklein07/blast-radius): AST localization, guarded renaming transformations, function execution coverage and import-time fingerprints. Useful separation of runtime bodies from definition-time effects; equivalence rules require source-reader/reflection analysis.
- [JuanQuenga](https://github.com/JuanQuenga/buildathon-blast-radius): per-patch fallback, batch budget, source-derived maps, cost-aware scheduling and optional runtime verification. Strong fail-safe architecture; runtime checking requires independent CPU measurements.

Unavailable (GitHub cache miss; first four also failed via raw README URLs):
- [CandyOre](https://github.com/CandyOre/Buildathon-RWX-Blast-Radius)
- [h-ardy](https://github.com/h-ardy/buildathon-blast-radius)
- [Not-Ethan](https://github.com/Not-Ethan/blast-radius-selector)
- [colinbenaissa](https://github.com/colinbenaissa/blast-radius-selector)
- [mike200004](https://github.com/mike200004/blast-radius-sel)
- [orbitautomation](https://github.com/orbitautomation/buildathon-blast-radius)
- [shobhit1kapoor](https://github.com/shobhit1kapoor/blast-radius-impact-selector)

Their algorithms/scores described in the user brief remain unverified here.
No competitor implementation source files were inspected or downloaded.

## Primary and general references

- [NameRTS paper abstract](https://arxiv.org/abs/2605.25356): element/name bipartite reachability avoids requiring a precise Python call graph; pruning uses execution/context information. Benchmark safety is not a guarantee for SQLGlot.
- [testmon](https://www.testmon.org/): execution-derived dependencies; requires a prior test run.
- [pytest-depper](https://github.com/ryx2/pytest-depper): AST dependency analysis.
- [pytest-impact](https://github.com/az-pz/pytest-impact): fixture/conftest-aware static selection.
- [Coverage contexts](https://coverage.readthedocs.io/en/latest/contexts.html): per-test execution attribution; code before the test context has an empty context and needs separate treatment.

## Technique matrix

Costs and usefulness below are engineering estimates, not measured target ablations.
All source-derived techniques are potentially legal only with independent code and
pinned-source metadata; copying competitor maps or patch answers is prohibited.
L/M/H denote approximate implementation effort, not guaranteed resource use.

| Technique / conceptual source | Problem and algorithm | Benefit | Failure modes | CPU / memory | Effort | Ours / score value |
| --- | --- | --- | --- | --- | --- | --- |
| File dependencies / depper | Reverse import reachability | Cheap broad candidate set | Dynamic imports, global side effects | Linear graph build/traversal | L | impact.py experimental; often too broad |
| Function/method dependencies / jklein07 | Map changed bodies to execution scopes | More precision than files | Defaults, callbacks, new paths | Scope index plus test sets | M | New locality classifier; map blocked |
| Name graph / NameRTS | Definitions and references connected through names | Avoid precise call graph | Name collisions, pruning assumptions | Many edges; caching useful | H | Deferred until basic evidence exists |
| Per-test line coverage / testmon | Map executed source lines to actual tests | Strong candidate precision | Setup, subprocess loss, new behavior | Full offline suite; compact inverted sets | M | Highest-value next evidence; blocked |
| AST differences / jklein07 | Separate body edits from module/def-header edits | Directs appropriate dependency evidence | Text readers, reflection, AST equality | Linear parse plus structural comparison | L | semantic.py implemented; no skip rule |
| Bytecode equivalence / sophiayuanproj | Compare compiled scopes | Suppress some textual noise | Python version, positions, source inspection | Compilation/code-object trees | M | Deferred; AST sufficient for locality |
| Import-time fingerprints / sophiayuanproj | Compare module/class state after import | Detect derived tables/metaclasses | Nondeterminism, serialization, side effects | Patched imports; potentially large snapshots | H | Deferred; unsafe to guess without target |
| Dynamic imports/inheritance / existing index | Expand dynamic targets and class relations | Prevent missing indirect dependencies | Strings, metaclasses, aliases | Registry/MRO edges | M | Existing global fallback; no verified target map |
| File/fixture reads / pytest-impact, sophiayuanproj | Track opens/listings and shared helpers | Preserve text/data observability | Child reads, native I/O, cached reads | Offline events and path-to-test sets | M | Required before textual no-op exclusion |
| Candidate execution / JuanQuenga | Test patched candidates under budget | Can reduce simulated work | Charged CPU, isolation, timeouts | Runtime test processes/RAM | H | Deferred pending evidence and Docker |
| Fallback / JuanQuenga | Missing/ambiguous evidence selects all | Limits false-negative risk | Over-broad fallbacks erase gains | Small overhead; full simulated CI | L | Active all-tests production; essential |
| Scheduling / official starter | LPT for k=1..8, compare makespan+2k | Direct cost improvement | Heuristic not exact partitioning | Small fixed worker factor | L | Verified 1104.510 vs 1210.470 s |

## Decision

Preserve production LPT. Add independent AST locality analysis now. It reports
body scopes, definition-time/module structural changes, parse uncertainty and
textual observability. AST-equal comments/formatting never authorize skipping.
This component cannot create target coverage, resolve dynamic SQLGlot behavior,
or prove a candidate set complete.

Preferred future hybrid: validated transitive static candidates UNION measured
execution candidates UNION import-time/file-read candidates, followed by fallback
and existing LPT. Every metadata channel needs revision and test-catalog identity.
Missing channels must broaden selection, not silently become empty sets.

Rejected for this milestone: AST-equality skipping (text remains observable),
copying competing metadata (rules), and speculative runtime execution (no measured
net benefit or working container). Coverage, bytecode and name pruning are deferred,
not empirically rejected. No competitive narrowing score was measured this phase.

## Phase 5 choices

| Technique | Decision and reason |
| --- | --- |
| Per-test execution and file reads (CandyOre, h-ardy, shobhit1kapoor) | Collect function entries and fixture/source opens independently. Include file-wide setup, child process uncertainty and shared import work. |
| Local semantic changes (jklein07, colinbenaissa) | Require validated context and a matching AST skeleton before body-level selection. Existing fixture changes require observed readers. |
| Bytecode and class state (sophiayuanproj) | Defer. Class attributes, registration and defaults currently trigger full fallback. |
| Runtime probing (Not-Ethan) | Defer. The current runtime has no database or test-runner dependencies and never executes patches. |
| Worker optimization | Retain measured LPT. Candidate membership is the dominant cost. |

The offline collector, its evidence and the runtime were implemented from the pinned upstream source. Public competitor scores were excluded from the ablation.
