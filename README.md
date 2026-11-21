# RWX Blast Radius

For each SQLGlot patch, the submission reconstructs the modified source and selects numbered tests using a pinned execution index. The scheduler tries one through eight workers and minimizes the official makespan plus worker charge. The production image needs only the Python standard library.

## Verify a checkout

    python -m unittest discover -s tests -v
    python benchmark.py
    python benchmark.py --details
    make sample
    make check

The last two commands require Docker, GNU Make and python3. The Makefile runs the linux/amd64 image offline as nobody with the competition limits. The benchmark compares full-suite, file-level and function-level selection on the same 30 public patches. See docs/PROGRESS.md for measured results and docs/ARCHITECTURE.md for evidence collection and limitations.

On the 30 public samples the hybrid scores **204.090 simulated seconds with zero misses**, down from 1104.510 for the full-suite scheduler.

## Reproduce the index

From the repository root in a Linux shell with Docker and Git, run the following. Collection runs twice in a disposable container. Allow several minutes and 6 GB of memory. The submission build uses the committed index.

    mkdir -p .phase5
    git init .phase5/sqlglot
    git -C .phase5/sqlglot fetch --depth=1 https://github.com/tobymao/sqlglot.git eb11aec4be8cb2122afe713a4816662c3f0fb2fa
    git -C .phase5/sqlglot -c core.autocrlf=false archive --format=tar -o ../src.tar eb11aec4be8cb2122afe713a4816662c3f0fb2fa
    docker build --platform linux/amd64 -f tools/Dockerfile.trace -t phase5-trace blast-radius-sample
    docker run --rm --platform linux/amd64 --cpus 4 --memory 6g -v "$PWD:/repo" phase5-trace sh /repo/tools/collect.sh

Generate the two optional narrowing indexes with the same archive and image:

    docker run --rm --platform linux/amd64 --cpus 5 --memory 6g -v "$PWD:/repo" phase5-trace sh /repo/tools/collect_lines.sh
    docker run --rm --platform linux/amd64 --cpus 5 --memory 6g -v "$PWD:/repo" phase5-trace sh /repo/tools/collect_predicates.sh

For independent mutations run the container with command `python /repo/tools/mutate.py <case>`, where the case is `function`, `fixture`, `lambda`, `nested`, `block_fixture` or one of the `comment_*`, `attr_*`, `base_*` and `registry_*` cases listed in tools/mutate.py, and environment `-e SKIP_INTEGRATION=0 -e OPENBLAS_NUM_THREADS=1`. Give each run at least 3.5 GB of memory; 2 GB is killed. Mutated suites are expected to fail. Then run `python tools/check_mutations.py`. The reports and generated diffs stay in .phase5/ outside the submission image.

## Submission

Use the public repository https://github.com/bob-the-doorknob/plingplong and the full validated commit SHA at the [official track](https://www.joinbuilders.org/buildathon/tracks/blast-radius). The accepted all-tests revision is `205133366ef9ed2be41a56ac606a51b5d5ac6d5e`.
