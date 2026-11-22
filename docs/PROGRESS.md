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

    git remote add origin https://github.com/bob-the-doorknob/plingplong.git
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

Git completion: verified foundation committed as
 af95ca46ae016311506a9f37dfc8fc462bb01496
and pushed successfully to origin/main. git ls-remote confirmed matching SHA;
working tree clean after push. Current Git safe.directory entry already present.

Leaderboard blocker: unauthenticated GitHub repository API returns HTTP 404,
consistent with the known private repository. Public access is required; visibility
was not changed. Browser automation reports access host unavailable, so no signed-in
submission flow could be reached. No leaderboard submission or score is claimed.
User can make the repository public in GitHub Settings, then enter the repository
URL and verified commit on the RWX track page. First submission remains priority
ahead of coverage development. No hybrid work was started this session.

## Phase 4: exact Make target verified - 2026-11-21

Fresh session runs as Andrew. Git status clean before checkpoint; origin/main
matches 4dde8aeee4281325428ebcc126c174e22ee76b27. GitHub remote is NOT empty:
the foundation and push-status documentation commits are present. Docker Engine
29.8.0 works; Ubuntu and docker-desktop WSL distributions are available.
Unauthenticated GitHub API still returns 404 for this known-private repository.
No ACL/ownership/security changes made; safe.directory already configured.

30 existing unittest tests passed. Host benchmark: 1104.510 s, zero misses,
0.015625 host CPU seconds. All-tests selector remains unchanged.

GNU Make was absent; sudo is unavailable. Downloaded Ubuntu make 4.4.1-3 package
with apt-get download and unpacked it in WSL user space (no administrator or
system package changes). Usable executable: /home/andrew/usr/bin/make.
Exact successful verification command from Windows PowerShell:

    wsl -d Ubuntu -- /home/andrew/usr/bin/make -C /mnt/c/Users/Andrew/OneDrive/Documents/NTU_code/Buildathon sample

Target built linux/amd64 image and executed the full official Docker restriction
flags, then score.py: 1104.510 simulated seconds, zero misses. This supersedes the
historical 'Make unavailable / equivalent commands only' limitation. Container
CPU not measured. Output remains 30 valid JSON lines / 210840 bytes.

Added .env ignore patterns; no production code changes. Runtime image includes
only selector.py beyond the pinned base. Experimental modules remain disabled.
Repository is small (tracked bytes checked below 20 MB); generated stdout,
archives and Python caches remain ignored. No tracked env/private-key filenames.

Remaining manual actions: GitHub Settings > General > Danger Zone > Change
repository visibility > Public, then sign in to the official RWX track, submit
https://github.com/bob-the-doorknob/plingplong with the final checkpoint SHA and
wait for an accepted practice result. Visibility and submission not performed.
No coverage work until a first valid submission is confirmed. Browser access was
unavailable in preceding checkpoint; no authenticated leaderboard session here.

## Phase 5 production candidate

The accepted all-tests commit 205133366ef9ed2be41a56ac606a51b5d5ac6d5e derives commit IDs from filenames and reuses one full schedule. Its user-reported official result was 1472.8 seconds for 40 commits with zero misses. The public sample below has 30 commits.

| Public sample variant | Simulated seconds | Host CPU seconds | Missed commits | Mean tests | Full fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full suite LPT | 1104.510 | 0.000 (clock resolution) | 0 | 1620.00 | 30 |
| File-level execution and readers | 864.461 | 0.453 | 0 | 1242.93 | 23 |
| Semantic function entries, static test importers and readers | 644.726 | 0.375 | 0 | 746.97 | 13 |

Pinned SQLGlot with Python 3.13.18 passed 1620 numbered tests and 25440 subtests with one organizer skip. Reversing test order produced failures in two parent IDs, both retained in every narrowed selection. Worker shards were observed for the optimizer and executor test files. The 1041609-byte index covers 215 original source and fixture files. It contains 5455 observation and static-dependency keys.

The final 13 fallbacks comprise eight structural or textual Python edits, three unsupported diffs, one shared or missing observation and one fixture text edit. Largest selection was 1620. Worst simulated commit cost was 36.817 seconds. Two complete independently mutated suites yielded 37 failing IDs for the serialization mutation and one for the optimizer fixture mutation. All were selected, among 184 and four candidates respectively.

36 project tests passed. WSL make sample passed under the official isolation flags. Three restricted container repeats produced identical 98319-byte stdout, median selector CPU 0.436 seconds, maximum peak RSS 48396 KiB and wall time below 0.49 seconds per selector. Local simulated time improved by 459.784 seconds (41.63%). This candidate awaits user authorization for a practice leaderboard run. The accepted competition entry remains the previous revision.

## Phase 6: finer scopes and fixture comments - 2026-11-21

Baseline reproduced at 09f90b6 on macOS arm64 (host Python 3.14.7): 36 tests passed, 644.726 s, zero misses.

Changes, both general rules with no sample identifiers:

- semantic.py: nested functions and lambdas are scopes keyed by CPython co_qualname. All 3691 split names in the 215 pinned files were verified to be real code object qualified names. This narrows a nested closure whose factory runs at import time, and a lambda in a class-level table.
- hybrid.py: an SQL fixture that contains a block comment no longer falls back unless an edited line holds a delimiter. Unterminated block comments are stripped to the end of the file.

| Public sample variant | Simulated seconds | Missed commits | Mean tests | Full fallbacks |
| --- | ---: | ---: | ---: | ---: |
| 09f90b6 hybrid | 644.726 | 0 | 746.97 | 13 |
| Phase 6 hybrid | 542.644 | 0 | 585.47 | 10 |

43 project tests passed. make sample passed with the official flags: 542.644 s, zero misses, and make check printed format ok. SAMPLE and OUTPUT were overridden to a path without spaces, because the Makefile does not quote the volume paths and this checkout path contains spaces and an ampersand. Container stdout was 77392 bytes, byte-identical to the host benchmark and across three restricted runs. Under amd64 emulation on arm64 the median selector CPU was 0.756 s, against 0.594 s for 09f90b6 on the same setup. Peak RSS was 57684 KiB. Emulated CPU is higher than native amd64.

Five full-suite mutations in the trace image (SKIP_INTEGRATION=0). All failures were selected by tools/check_mutations.py:

| Case | Target | Failing IDs | Selected |
| --- | --- | ---: | ---: |
| function | serde.py body | 37 | 184 |
| fixture | eliminate_joins.sql | 1 | 4 |
| lambda | SQLiteGenerator TRANSFORMS lambda | 2 | 11 |
| nested | build_regexp_extract.<locals>._builder | 2 | 121 |
| block_fixture | qualify_columns.sql, which has block comments | 1 | 4 |

The remaining 10 fallbacks are as follows. Three are comment-only patches. Three multi-file patches each include a comment-only Python file. AGENTS.md requires all tests for comment-only changes, so these six were left unchanged. Four are class-level constants or import-time call arguments. Narrowing those needs evidence of attribute reads. Static load-name readers alone are not enough: the dialect metaclass and class bodies read many such attributes at import time, and there are 22 dynamic getattr, dir, vars or __dict__ sites that need an audit.

## Phase 7: AST-based comment-only rule - 2026-11-21

The team relaxed the comment-only rule in AGENTS.md, provided it passed empirical validation. A sqlglot .py file whose ast.dump is unchanged after reconstruction now selects only hits[path] plus hits['!untraced']. It no longer forces a full fallback of a multi-file patch. A shared reader, a failed reconstruction or coding[:=] on line 1 or 2 still selects the full suite.

Evidence for hits[path] on Python files, checked before writing the rule:

- The index has 15 .py reader keys and none contains -1. The readers are tests/dialects/test_dialect.py::TestDialect::test_enum for dialect.py (warning formatting through linecache) and tests/test_typing.py::TestTyping::test_no_redundant_expression_metadata for 14 sqlglot/typing files (read_text, then ast.parse).
- Imports appear only as 183 sqlglot/**/__pycache__/*.pyc keys, all shared [-1]. compileall runs before collection, and imports run in the shared context.
- A probe in the trace image confirmed this. Importing sqlglot.dialects.tsql opened only .pyc files. inspect.getsource and warnings.formatwarning opened tsql.py. A second, cached getsource opened nothing.
- tests/test_docs.py uses load_tests, which pytest ignores, so no doctest IDs are in the catalog. sqlglot itself never reads its own source, frames or line numbers, and no pinned file has an encoding cookie.

Mutations: the targets came from grepping tests/ for inspect|getsource|linecache|__file__|co_firstlineno|traceback, plus parser, generator and optimizer files drawn with random.Random(20261121). Each comment-only case inserts a comment on line 1 and one inside the function body nearest the middle of the file. Eight full-suite runs were made; all failures were selected:

| Case | Files | Failing IDs | Selected |
| --- | --- | ---: | ---: |
| comment_dialect | dialects/dialect.py | 0 | 3 |
| comment_typing | all 15 sqlglot/typing files | 0 | 4 |
| comment_tokens | tokens.py | 0 | 3 |
| comment_core | __init__.py, expressions/core.py, parser.py | 0 | 3 |
| comment_trino_parser | parsers/trino.py | 0 | 3 |
| comment_dune_generator | generators/dune.py | 0 | 3 |
| comment_isolate_table_selects | optimizer/isolate_table_selects.py | 0 | 3 |
| comment_mixed | generator.py comment plus the serde.py function mutation | 37 | 184 |

The five earlier mutation reports still pass under the new code.

| Public sample variant | Simulated seconds | Missed commits | Mean tests | Full fallbacks |
| --- | ---: | ---: | ---: | ---: |
| 14d06ec | 542.644 | 0 | 585.47 | 10 |
| Phase 7 | 346.876 | 0 | 267.77 | 4 |

51 project tests passed. make sample: 346.876 s, zero misses; make check printed format ok. Container stdout was 36347 bytes, byte-identical to the host benchmark and across three restricted runs. Median selector CPU under amd64 emulation was 0.903 s, against 0.756 s for 14d06ec. Peak RSS was 57724 KiB. The remaining four fallbacks are class-level constants or import-time call arguments.

Residual risk: linecache caches source across tests. A test that reads a cached file without opening it is not recorded as a reader. No current test reads sqlglot source through inspect, and sqlglot does not read it itself.

## Phase 8: class attribute evidence - 2026-11-22 (validation incomplete)

The tracer now injects a cooperative tracing metaclass through builtins.__build_class__ and installs __getattribute__ on root sqlglot classes. It records receivers, class-body attribute reads by their defining class, runtime class writes, import-time reads with the class under construction, and tests that change sqlglot module globals or class-level containers. owner() clears linecache. hybrid.decide narrows structural edits that are only class-level assignment values in non-core files, as described in AGENTS.md.

Evidence was rebuilt with tools/collect.sh: forward 399 s, reverse 393 s, 796 s in total. It matches the pin and the organizer IDs. The index is 1196139 bytes and the tracked repository is about 2.8 MB. Unit tests pass. benchmark.py gives 270.947 s with zero misses and one fallback (import_module_read).

Mutations: 12 of the 28 runs finished before the run was stopped, with no miss. These were the attr_* cases except attr_approx_quantiles_arg_types. Ten of the 12 had failing tests, and every narrowed case kept all its failures: 22/1216, 2/465, 2/419, 1/510, 3/369, 2/5, 2/541 for the generator cache case, and 1/347 selected. attr_mysql_tokenizer_quotes and attr_lateral_arg_types fell back to the full suite. Not yet run: attr_approx_quantiles_arg_types, base_parser_flag, base_generator_flag and the 13 earlier cases. make sample, make check and container CPU are also not yet measured. This commit is not a validated submission candidate.

## Phase 8 verification and Phase 9 import proof

Started from main 41fcbedfeda2ccc700b97d992a36431d0102b545 in an isolated
phase9-import-proof worktree. Phase 8's AST classifier raised AttributeError
on Python 3.11, which lacks ClassDef.type_params. Defaulting the absent field
to an empty list reproduces the Linux/Python 3.13 behavior. A literal class
assignment that changes literal type or starts evaluating an expression now
falls back. Replacing the pinned Hive tokenizer escape list with None raised
during class creation and produced 34 pytest collection errors. Phase 8
selected 510 tests on that patch. Phase 9 selects all 1620.

| Public sample variant | Simulated seconds | Container CPU median (s) | Misses | Fallbacks | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase 7 | 346.876 | 0.831 | 0 | 4 | 267.77 |
| Phase 8 | 270.947 | 0.689 | 0 | 1 | 134.77 |
| Phase 9 | 236.606 | 0.699 | 0 | 0 | 80.97 |

All 69 project tests passed on host Python 3.11 and container Python 3.13.18.
Exact make sample and make check passed for Phase 8 and Phase 9 in WSL.
Three restricted runs per variant produced identical bytes within each variant.
Phase 8 emitted 19232 bytes, with peak RSS 54388 KiB. Phase 9 emitted 12260 bytes,
with peak RSS 54332 KiB and selector wall time up to 0.794 s. These are local
linux/amd64 measurements. Source-derived evidence retains the Phase 8 blob
d0336a88899cf77f6455f9f036b6995b7a5a1275 from the pinned SQLGlot revision.

The remaining Phase 8 fallback was an observed read of TriggerProperties.key
when constructing expressions.EXPR_CLASSES. The changed value influences
required_args, while key comes separately from the class name. The Phase 9
dependency proof avoids only the unaffected module edge under the conditions
stated in ARCHITECTURE.md. Independent review checked 163 matching source
definitions and identified that the packed ancestry filters external classes.
The implementation now also requires an explicit sole Expression base in the
AST, and tests cover subclasses and downstream import consumers.

Three public patches each cost 27.454 s. They select test_execute_tpcds
(21.454 s) through execution of Dialect.case_sensitive,
_should_eliminate_join or serde.dump. Static test importers add 112 tests to
the dialect patch. A separate one-test probe confirmed TPC-DS actually enters
all four expensive affected functions, including Context.table. All 30
LPT schedules meet the lower bound from the longest test and mean worker load.
The remaining opportunities are selection precision, including attribution to
individual executor tests, and safe net savings from runtime verification.

### Mutation matrix

All 28 original cases completed, plus three independent registry mutations.
The 31 completed cases produced 155 failing test IDs across case
runs, all retained by both Phase 8 and Phase 9. An additional Hive type mutation produced 34
collection errors in pytest and is inconclusive for numbered labels. Phase 9
selected the full suite for that patch. Eight cases were retried after fixing
a harness syntax error. Reproduce any case with the commands in README.md.

| Case | Kind | Pytest exit | Failing IDs | Selected | CI seconds | Selection reason | Omitted IDs |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| attr_approx_quantiles_arg_types | Class attribute | 1 | 4 | 1620 | 36.817 | import_module_read | None |
| attr_bigquery_log_base | Class attribute | 1 | 2 | 419 | 16.038 | observed | None |
| attr_bigquery_parser_functions | Class attribute | 1 | 1 | 347 | 14.067 | observed | None |
| attr_duckdb_null_ordering | Class attribute | 1 | 22 | 1216 | 27.454 | observed | None |
| attr_duckdb_transforms | Class attribute | 1 | 2 | 541 | 27.454 | observed | None |
| attr_hive_date_format | Class attribute | 0 | 0 | 510 | 16.300 | observed | None |
| attr_hive_generator_decode | Class attribute | 0 | 0 | 311 | 12.686 | observed | None |
| attr_hive_invalid_escapes | Class attribute | 2 | Inconclusive | 1620 | 36.817 | structural_or_text | Unlabeled |
| attr_hive_parser_log | Class attribute | 1 | 2 | 5 | 2.494 | observed | None |
| attr_hive_tokenizer_escapes | Class attribute | 1 | 1 | 510 | 16.300 | observed | None |
| attr_lateral_arg_types | Class attribute | 1 | 5 | 1620 | 36.817 | import_module_read | None |
| attr_mysql_tokenizer_quotes | Class attribute | 1 | 6 | 1620 | 36.817 | import_module_read | None |
| attr_postgres_index_offset | Class attribute | 1 | 2 | 465 | 16.387 | observed | None |
| attr_postgres_parser_json | Class attribute | 1 | 3 | 369 | 14.493 | observed | None |
| base_generator_flag | Core class attribute | 1 | 10 | 1620 | 36.817 | structural_or_text | None |
| base_parser_flag | Core class attribute | 1 | 1 | 1620 | 36.817 | structural_or_text | None |
| block_fixture | Fixture | 1 | 1 | 4 | 3.804 | observed | None |
| comment_core | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_dialect | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_dune_generator | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_isolate_table_selects | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_mixed | Text and function | 1 | 37 | 184 | 27.454 | observed | None |
| comment_tokens | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_trino_parser | Source text | 0 | 0 | 3 | 2.398 | comment_only | None |
| comment_typing | Source text | 0 | 0 | 4 | 2.409 | comment_only | None |
| fixture | Fixture | 1 | 1 | 4 | 2.503 | observed | None |
| function | Function body | 1 | 37 | 184 | 27.454 | observed | None |
| lambda | Function body | 1 | 2 | 11 | 2.732 | observed | None |
| nested | Function body | 1 | 2 | 121 | 6.146 | observed | None |
| registry_clone | Registry state | 0 | 0 | 7 | 2.946 | observed | None |
| registry_in_place | Registry state | 1 | 7 | 1620 | 36.817 | structural_or_text | None |
| registry_trigger_event | Registry state | 1 | 7 | 10 | 2.480 | observed | None |

## Phase 10 checkpoints

| Checkpoint | SHA | Simulated (s) | Median CPU (s) | Public misses | Mean tests | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Phase 9 | 126d08304548e3aadff3c285ab5d4db40ed9d66c | 236.606 | 0.699 | 0 | 80.97 | Verified baseline |
| P10-A | See baseline profiling commit | 236.606 | 0.767 | 0 | 80.97 | Reproduced |

P10-A ran 69 tests, make sample, make check and three identical restricted
runs. Maximum peak RSS was 54328 KiB and maximum selector wall time 0.892 s.
Three patches cost 27.454 s each, followed by 25.454 s and 16.155 s. The first
four select TPC-DS at 21.454 s. The fifth uses 498 tests and has an 8.155 s
makespan. See benchmark.py --details for per-patch evidence. The plan is to
collect independent line coverage, score narrow statement edits, then use
measured costs to decide whether runtime probes merit an experiment.

P10-B adds a separate 281923-byte line index with 53027 observed source lines
from two organizer-compatible orders. Missing or shared spans retain function
coverage. Same-shape literal and operator edits use the original condition or
statement span. Insertions, deletions, lambda edits and definition-time edits
retain the earlier behavior.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-B | 234.442 | 0.950 | 235.392 | 0 | 78.37 |

The linux/amd64 Make targets and three identical restricted runs passed.
Peak RSS was 77636 KiB, selector wall time was at most 1.032 s and stdout
was 11968 bytes. The 31 completed Phase 9 mutations kept all 155 failures.
New comparison and guard mutations kept 52 failing IDs. The additional
optimizer boolean mutation completed without failures. Rebuild the line index
with the same trace image as README.md and /repo/tools/collect_lines.sh.

P10-B index verification was repeated with startup and exit manifests for
every traced Python process. Both suite orders produced the exact previously
committed line index blob 9c019d24bd9db238944145c23ee28adcd4d8005b. This
checks collected child-process completion in addition to test outcomes.

P10-C records whether identity and equality transports return the same bool
at an operand pair with audited native comparison slots. The offline AST
instrumentation retains operand evaluation order and the original operator
result. The group index requires agreement for the individual test in both
suite orders. Any divergence or unsupported observation blocks that test.
Shared ambiguities block the site. Pool tasks carry their submitting test ID
and all started interpreter shards must complete. Test importers, text
readers and untraced tests are kept independently of this evidence.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-C | 204.090 | 1.004 | 205.094 | 0 | 74.00 |

P10-A is 0bf39c25e32b2b0542bc91790dc1d27917d5b9a8. P10-B is
9b02a4e54594d185de5e81cd7c76d52412aab6bc, with collection hardening in
fbbf7c90934183618a2aa656b1618da046e823e6. The predicate index is 33578 bytes.
Its baseline instrumented run passed all 1620 numbered tests. Reverse order
reproduced the two known parent failures. Restricted Docker emitted
11311 identical bytes in three runs, at most 78664 KiB peak RSS and 1.068 s
selector wall time. Both Make targets and 77 unit tests passed.
One independent identity mutation retained all 6 failing IDs. A second
completed without failures. The Hive collection error remains inconclusive.
A development-only oracle computed with the public scorer was 94.351 s.

A restricted single-test TPC-DS run passed all 57 subtests and used 22.170 s
CPU at 15.987 s wall time. For an independent optimizer mutation, the
optimizer-only probe produced 57 unchanged expression graphs at 2.401 s
CPU, compared with 2.991 s for the original. This measures a bounded stage.
The probe does not reproduce executor input serialization, plan execution
or the DuckDB comparison. It supplies no exclusion evidence to production.

P10-D uses the submitting test ID inside each worker task. Startup and exit
records must match, and both suite orders must show attributable SQLGlot
execution in the optimizer and executor pools. Worker initialization still
uses the test-file context. Line selection and operand agreement apply
independently, and ambiguous tests retain their separate protection.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-D line only | 214.161 | Unmeasured | Unmeasured | 0 | 60.70 |
| P10-D integrated | 169.621 | 0.940 | 170.561 | 0 | 56.13 |

P10-C is 832d0529c6528f1b01bc1ca2835788dbd81b3ed6. The P10-D line map is
283635 bytes. Both WSL Make targets passed, as did three identical 8620-byte
restricted runs. Peak RSS was 72884 KiB and maximum selector wall time 0.996 s.
The independent mutation matrix retained every labeled failure.
The fresh-table copy experiment was kept out of this candidate. Its first
trial saved 0.156 simulated seconds, and review identified constructor
wrapping as a possible escape of the otherwise fresh object.

P10-E narrows an isolated radix edit to one existing entry in a literal
NUMERIC_ESCAPES map. The pinned import and generation sites use key
membership or truthiness. Reads of the radix occur only in the tokenizer's
two numeric helpers. Missing scope coverage, shared reads, unfamiliar
initializers, reflective readers and runtime attribute writes retain
conservative coverage. The change uses original source and line/function
evidence across all dialects and never reverse engineers the failing IDs.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-E | 159.754 | 0.891 | 160.645 | 0 | 40.40 |

P10-D is 0144122cb13a27f1e446d18cfc1875b0e67e8aa1. E passed 82 unit tests,
both Make targets and three identical 6533-byte runs. Peak RSS was 73140
KiB and maximum selector wall time 0.952 s. Five separate numeric mutations
completed and retained all observed failures. DuckDB, Snowflake and
ClickHouse selected via the new rule, with no observed failing tests. Spark
and the failing Postgres case retained class-based selection. Review found
no pinned reflection or persistent cache of decoded results. Cross-test
state remains an empirical assumption.

P10-F projects isolated nonzero week-offset edits onto all five pinned
arithmetic and formatting reads. Missing line evidence, class writes,
generic import-time consumers and zero or out-of-range values preserve
class-based coverage. Review confirmed no cached derived week value in the
pinned consumers and identified the old optimizer-wide class attribution
as the source of most avoidable candidates.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-F | 147.238 | 1.021 | 148.259 | 0 | 29.60 |

P10-E is 5ef6ad182655aeb78a32ab7ce7f4b1d29519c669. F passed 83 unit
tests and both Make targets. Three restricted runs emitted identical 5038
bytes, at most 88492 KiB peak RSS and 1.070 s selector wall time. The three
independent week mutations completed. The BigQuery failure was kept among
13 tests. The Teradata zero edit used the class fallback and kept its one
failure. Oracle had no failures.

P10-G matches Boolean regrouping when the ordered leaf expressions are
unchanged and an original executable statement anchors the edit. Candidates
come from the full original statement span. Unmapped or shared spans keep
function coverage. The independent canonicalize guard mutation retained all
17 failing IDs among 69 selected. Review found no pinned first-divergence
counterexample.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-G | 138.664 | 0.984 | 139.648 | 0 | 17.47 |

P10-F is 01a7922543f8a420558ea555119b67a31cc64481. P10-G passed 84 unit
tests, both WSL Make targets and three identical restricted runs. Maximum
selector wall time was 1.062 s, peak RSS was at most 88532 KiB and stdout
was 3214 bytes. No public patch selected the full suite. All 46
completed mutations retained their 233 failing IDs across case runs.
The Hive collection-error case remains inconclusive.

P10-H removes a historical blanket guard only when an existing patch is
disjoint from a certified direct Python child's file footprint. Matching
startup, exit status and per-process reports in both suite orders are
required. Every independently recorded executed SQLGlot path must appear
in the child's audited file footprint. Other evidence can still select
the same test, and the reverse-order safety guards remain active.

| Checkpoint | Simulated | Median selector CPU | Total | Public misses | Mean tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| P10-H | 129.530 | 1.081 | 130.611 | 0 | 16.57 |

P10-G is 96a1071bb32eb669192cf8b96ba920ebd509a306. H passed 86 tests
on both host and Linux Python, plus make sample and make check. Three
restricted runs emitted identical 3104-byte stdout. Peak RSS was 88664
KiB and selector wall time was at most 1.139 s. Of 48 mutation cases,
47 completed and retained all 234 failing IDs. The eager-import mutation
failed the direct subprocess test and retained it through the structural
fallback. The earlier Hive collection-error case is inconclusive.

The hardened collection certified one direct test in both orders. Forward
order passed 1620 numbered tests. Reverse order retained its two known
parent failures. The shipped line index is 283942 bytes. The local score
is 106.694 seconds below the Phase 9 measured total. The two remaining
public TPC-DS selections are required by the public failure labels.
Removing all three earlier blanket guards in a development-only ablation
would still leave 119.590 simulated seconds before CPU. The ablation is
not part of the selector.

## Phase 11: generalization benchmark - 2026-11-22

Started from Phase 10-H (32a3fe450d5f307703a4691f9180a235f49c46f3).
Fetched main at 8e48a59da0964d3f1955abd68c01821373797c14 with an identical
tree. The Phase 10-H public reproduction was 129.530 simulated seconds,
zero misses, zero full-suite fallbacks, 86 tests passed, and successful
Make sample and format checks. Three runs on this host had a median
1.155 CPU seconds, up to 88488 KiB RSS and identical 3104-byte output.

The two reported practice results cost 334.724 and 344.968 simulated
seconds with zero misses. Their submitted SHAs are unknown. The public
result normalizes to 172.707 seconds per 40 patches, a batch-size
diagnostic only. Almost all the reported difference is simulated CI.
The site exposes no per-patch practice decisions.

All Phase 10-H full-suite paths:

| Reason | Trigger |
| --- | --- |
| catalog | Missing, unreadable, wrong-revision or mismatched test-ID evidence |
| unreadable_patch | Invalid UTF-8, I/O failure or analysis recursion limit |
| unsupported_diff | Unindexed path, nonstandard header, malformed hunk or context/position mismatch |
| invalid_python / encoding_cookie | Syntax/compile error or a potentially significant encoding declaration |
| fixture_text / unobserved_fixture | Fixture comment-only, SQL block delimiter change or absent readers |
| structural_or_text | Signature, import, runtime binding, new/deleted class or method, core class value or opaque semantic change |
| class_evidence / unobserved_class / unobserved_attribute | Missing class metadata, receivers or observed reads |
| import_module_read | Import-time class dependency reaches unattributed module state |
| unobserved_scope | Changed code object's qualified name has no observation |
| shared_or_missing | Unattributed execution or raw-reader evidence, or no observed candidate for a code change |
| unknown | Indexed fixture path without a supported language or file type |

An unsupported statement or predicate annotation keeps function
coverage. It is a full-suite fallback only when broader evidence also
fails. Additions, deletions, renames, copies, modes, binary edits and
quoted paths lack the same-path reconstruction proof. Zero-context and
multihunk edits are validated against exact pinned content and positions.

The new tools/generalization.py harness verifies the archive, pins
organizer pytest, checks the entire collection and expected skips, and
scores with the official scorer. It freezes development and holdout
cases. Missing reports, timeouts, collection errors and unexpected skips
are inconclusive. Ground-truth labels and generated patches remain in
.phase5, outside the production image.

### P11-B: exact Git text reconstruction

Changed-file detection and application use LF as Git's line delimiter.
CRLF payload and missing-final-newline markers are preserved. Uniform CRLF
transport is distinguished from payload. Invalid framing and context still
fall back. Both changes are general patch-format support.

The parser-only staged tree passed 92 unit tests and both Make targets.
The public score stayed at 129.530 seconds with zero misses. Three
restricted runs emitted identical 3104-byte outputs. Under concurrent
mutation labeling, median selector CPU was 1.565 seconds and peak RSS
was 88540 KiB. The first two independently completed newline-marker
mutations saved 9.363 seconds each and retained all 325 failing parent
IDs across those two runs.

### P11-C generalization candidate

The pinned generator builds a dispatch cache per exact receiver class.
A plain literal-return _sql override appended to a direct leaf Generator
can use that receiver's coverage. Source readers, static importers,
uncertain tests and existing ordering guards stay selected. Related
import-time reads, attribute writes, subclasses and other structural
edits keep the usual fallback. No index regeneration or runtime test
execution was needed.

| Version | Public 30 CI (s) | Public CPU (s) | Holdout 17 CI (s) | Holdout CPU (s) | Holdout full fallbacks | Holdout mean tests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 10-H | 129.530 | 1.073 | 563.818 | 0.358 | 13 | 1260.88 |
| P11-B parser | 129.530 | 1.145 | 554.455 | 0.317 | 12 | 1185.06 |
| P11-C integrated | 129.530 | 1.059 | 500.525 | 0.547 | 10 | 1003.47 |

CPU is the median of three restricted Linux/amd64 runs per dataset and
image. All public and holdout runs had zero misses. The holdout total
including CPU is 501.072 seconds, down from 564.176. All three C public
outputs were identical at 3104 bytes, the holdouts at 74660 bytes, and
the full independent inputs at 129856 bytes. Peak RSS across those
candidate runs was 90104 KiB and the longest selector wall time was
1.166 seconds. Both official Make targets and all 96 unit tests passed
on the host and in the locked Linux test image.

All 32 generated patches passed Git apply validation against the pinned
index. The clean label run collected 1620 numbered tests and the one
organizer skip. Of 32 mutations, 31 completed with all 1083 failing
parent IDs retained, including 805 across all 17 holdouts. The other
case, trie_default, had 56 collection errors and used all 1620 tests.
The 31 labeled cases cost 845.502 seconds versus 944.289 for H. Full
selections fell from 21 to 16, mean selections from 1137.52 to 902.71.
The 47 completed earlier mutations also retained all 234 failing IDs.
The earlier separate Hive collection-error case remains inconclusive.

| Category | Completed cases | Phase 10-H CI (s) | P11-C CI (s) | Saved (s) |
| --- | ---: | ---: | ---: | ---: |
| Method added | 4 | 147.268 | 67.207 | 80.061 |
| Module global | 2 | 73.634 | 73.634 | 0 |
| Test side | 2 | 73.634 | 73.634 | 0 |
| Missing final newline | 2 | 73.634 | 54.908 | 18.726 |
| Control flow | 2 | 50.271 | 50.271 | 0 |

The three narrowed overrides selected 106 SQLite, 33 Dremio and 120
Oracle candidates. They retained 68, zero and two independently
observed failures, respectively. The equivalent SQLite override
inserted before existing class code deliberately used the structural
fallback. TPC-DS was selected on 26 completed cases by H and 23 by C,
and actually failed on nine. Both public TPC-DS selections are required
by the public labels. The largest remaining costs by category on this
matrix are module globals and test-side edits. Their import-time effects
and test collection need additional evidence.

P11-A is a39e15c7feb73ed2ed8430d9e3b5a273e1ba2a8e. P11-B is
2c44bc879b6e7fe552fddd6dc821d03009a3938c. The integrated candidate is
the commit containing this report on phase11-generalization. This
designed mutation suite is independent of the public labels. Its
category frequencies and scores provide no estimate of the private
practice or final distribution.

## Phase 12-0 local submission audit

Fetched main at 85b96c0, whose tree matches 62aecb11129a55406739ea271d5e354a4cb3a227.
A clean linux/amd64 Docker build from git -c core.autocrlf=false archive
at that SHA matched every production Python and evidence blob by SHA-256.
The first archive used host CRLF conversion on Python files. Rebuilding
without conversion removed the byte differences. The verified image
uses Python 3.13.18 and is sha256:2a9e99979fb092dae94616be3a17bff8e83902288eff0a20ef43eab6e4fe505f.
Use tools/provenance.py COMMIT IMAGE DIAGNOSTIC_PATCH_DIRECTORY to repeat
the digest audit with production limits and inputs mounted read-only.

The diagnostic output digest is b2f4f65867dce129343cf8dbb1ceb98d04b5a85059974cbc3a804db83c966cab.
The newline case selected 331 tests. The three supported generator
overrides selected 33, 106 and 120, while the unsupported structural edit
selected 1620. All three restricted runs on the 17 holdouts scored 500.525
simulated seconds with zero misses. Production rules are active locally.
The organizer's receipts and private decisions could not be verified.
The identical 334.724-second official simulated totals remain unexplained.

## Phase 12-A module scalar reads

The static packer derives exact direct function readers of a scalar
from the pinned source and binds the certificate to the original
coverage digest and organizer catalog. The original and patched AST
must differ only in one same-type immutable assignment value. Imported
aliases, import-time and nested captures, reflective namespaces and
unresolved readers keep the full selection. The pinned certificate
currently covers nine serde bindings. The public and frozen holdout
simulated scores stayed 129.530 and 500.525 seconds with zero misses
in Docker. The existing serde development case and two fresh scalar
validation cases each saved 9.363 seconds. All 71 failing parent IDs
from those three cases were retained.

## Phase 12-B integrated candidate

The exact H image selected 1620 for all five provenance diagnostic
cases. The exact Phase 11 image narrowed four. The two verified
artifacts demonstrate that the local build runs the intended rules.
They provide no organizer-side image or per-patch attribution.

| Version | Public CI | Frozen holdout CI | Holdout median CPU | Holdout total | Holdout full fallbacks | New validation CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 11 / P12-0 | 129.530 | 500.525 | 0.594 | 501.119 | 10 | 220.902 |
| P12-A | 129.530 | 500.525 | 0.601 | 501.126 | 10 | 202.176 |
| P12-B integrated | 129.530 | 500.525 | 0.608 | 501.133 | 10 | 133.346 |

All measured public, holdout and new validation batches had zero
misses. The integrated public CPU median was 1.229 seconds. Each row
uses three restricted Linux/amd64 runs on the same input sets. The
frozen holdout mean remained 1003.47 selected tests and its output
was identical across all versions. All 805 known failures were retained.
The sub-400 holdout target remains open.

The new validation set contained six completed mutations. Terminal
assertions in two test modules saved 34.419 and 34.411 seconds and
retained both failing IDs. The test with the changed first argument
stayed full-suite. The exportable ANSI scalar also stayed full-suite.
The global and test-side rules saved 96.919 simulated seconds across
the 37 labeled development, holdout and validation mutations combined.
All 1122 failing parent IDs were retained. The inherited trie_default
collection failure stays inconclusive and selected 1620.

The pinned assertion scan certified 67 sites. Review found the draft
omitted source readers in the test-side return path. The released path
retains them, including full fallback for shared readers, and a
regression test covers both cases. The image passed both Make targets
and 101 unit tests. Peak RSS was 90584 KiB, the largest stdout was
140758 bytes, and public stdout stayed byte-identical at 3104 bytes.

Module captures, broader test methods, signature changes, import state,
mixed structural patches and file renames remain conservative. The
strongest evidence for the new techniques comes from the independent
validation set. No new official score was measured.
