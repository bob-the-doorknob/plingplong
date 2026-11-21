set -eu
mkdir -p /src /tmp/events
tar xf /repo/.phase5/src.tar -C /src
cd /src
export PYTHONPATH=/repo/tools:/src SKIP_INTEGRATION=0 OPENBLAS_NUM_THREADS=1
python -m compileall -q sqlglot tests
BR_TRACE=1 python -m pytest -q -p trace_plugin tests > /repo/.phase5/suite.log 2>&1
status=0
BR_REVERSE=1 BR_TRACE=1 python -m pytest -q -p trace_plugin tests > /repo/.phase5/reverse.log 2>&1 || status=$?
[ "$status" -le 1 ]
python /repo/tools/pack.py