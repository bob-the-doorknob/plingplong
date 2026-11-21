# RWX Blast Radius foundation

Conservative all-test submission with deterministic cost-aware LPT scheduling.
Target source revision: SQLGlot `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`.
The runtime does not import SQLGlot or use sample labels. No runtime dependencies
beyond Python; the official pinned Python 3.13 image is retained.

## Verification

Python 3.11 or newer on Windows or Linux:

```sh
python -m unittest discover -s tests -v
python benchmark.py
python score.py blast-radius-sample/sample blast-radius-sample/sample/answers.json output.jsonl
```

With pytest installed, `python -m pytest tests` runs the same tests.
The benchmark executes both entry points, measures host CPU/wall time, validates
with the unchanged official scorer, and writes UTF-8 output.jsonl without a BOM.
CPU numbers are coarse host measurements, not container/server totals.

With Docker Engine, GNU Make and python3 available (prefer WSL2):

```sh
make sample
make check
```

The root Makefile uses the preserved starter sample directory. Docker's original
linux/amd64 flags enforce offline, read-only, nobody, memory and process limits.
The root Dockerfile copies only selector.py. The starter remains unchanged under
blast-radius-sample/ and matches the supplied archive byte for byte.

## Measured sample results

2026-11-21, 30 commits, host Python 3.11.9, official scorer:

| Variant | Simulated seconds | Missed commits | Host CPU seconds | Notes |
| --- | ---: | ---: | ---: | --- |
| Unmodified starter | 1210.470 | 0 | 0.000000 | 3 workers |
| Starter selection, optimized scheduling | 1104.510 | 0 | 0.015625 | 4 workers |
| Static file impact | not run | unknown | unknown | pinned source unavailable |
| Dependency-aware selection | not run | unknown | unknown | deferred |

Both select 1620 tests / 103.047 recorded seconds per commit. Batch worker overhead
falls outside test load: 180 seconds baseline, 240 optimized. Net reduction is
105.960 seconds (8.75%). Measurements above are one host run, not the official
median of three container totals. The supplied archive's baseline differs from
the approximate 1614.1 in the task; no effort was made to force agreement.

## Container verification and submission

2026-11-21 environment recovery: this session runs as Andrew; Git metadata writes,
GitHub networking and Docker Engine are available. The safe.directory entry was
already configured. Origin is https://github.com/bob-the-doorknob/Buildathon.git;
fetch/ls-remote found an empty remote before the first commit.

The root Dockerfile built successfully for linux/amd64. Direct docker run with
all official Makefile isolation flags passed: network none, read-only root,
uid/gid 65534, HOME=/tmp, 64 MB tmpfs, 2 CPUs, 4 GB RAM/swap cap, 256 processes,
capabilities dropped and no-new-privileges. A host subprocess imposed 180 seconds.
Result: 30 valid lines / 210840 bytes, 1104.510 simulated seconds, zero misses;
Docker CLI wall time 0.413 seconds. This is local container evidence, not a
leaderboard result. GNU Make remains unavailable; its build/run/scorer steps
were executed directly. CPU accounting was not captured for this container run.

Production narrowing remains disabled. Only selector.py enters the image.
Before submission, make the repository public manually and submit the verified
commit hash. Visibility has not been changed. General event licensing requirements
still need checking; no license for supplied starter content was invented.

## Phase 2 current verification

Fresh scheduler reproduction: 1210.470 s starter, 1104.510 s optimized, zero misses
for all 30 sample commits. First host run CPU 0.015625 s for each; this coarse
Windows clock is not server/container accounting. New dependency-analysis tests
run with `python -m unittest discover -s tests -v` (20 passing at implementation).

impact.py is experimental and is not called by the submission. It exposes
build_index(checkout_path) and select_tests(diff_text, tests, index). No pinned
SQLGlot checkout could be fetched, so no claim of SQLGlot narrowing or improvement
is made. Scheduler and Docker payload remain unchanged. See architecture notes.

Latest verification: exact `make sample` passed under Ubuntu WSL on 2026-11-21,
1104.510 simulated seconds, zero misses. GNU Make is available as a user-local
unpacked Ubuntu package at `/home/andrew/usr/bin/make`; from PowerShell:

```powershell
wsl -d Ubuntu -- /home/andrew/usr/bin/make -C /mnt/c/Users/Andrew/OneDrive/Documents/NTU_code/Buildathon sample
```

The earlier Make-unavailable note describes the prior session. Public visibility
and an accepted leaderboard result remain manual submission gates.
