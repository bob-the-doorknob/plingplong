set -eu
mkdir -p /src /tmp/events
tar xf /repo/.phase5/src.tar -C /src
cd /src
export PYTHONPATH=/repo/tools:/src SKIP_INTEGRATION=0 OPENBLAS_NUM_THREADS=1
python -m compileall -q sqlglot tests
python /repo/tools/candidates.py /src > /tmp/candidates.json
start=$(date +%s)
BR_TRACE=1 python -m pytest -q -p trace_plugin tests > /repo/.phase5/suite.log 2>&1
middle=$(date +%s)
status=0
BR_REVERSE=1 BR_TRACE=1 python -m pytest -q -p trace_plugin tests > /repo/.phase5/reverse.log 2>&1 || status=$?
echo "forward $((middle - start)) s, reverse $(($(date +%s) - middle)) s" > /repo/.phase5/collect_time.txt
[ "$status" -le 1 ]
# Keep the raw observations so the index can be repacked without tracing again.
rm -rf /repo/.phase5/raw && mkdir -p /repo/.phase5/raw
cp -r /tmp/events /tmp/classes /tmp/pass0.json /tmp/pass1.json /tmp/collected.json /tmp/candidates.json /repo/.phase5/raw/
BR_RAW=/repo/.phase5/raw python /repo/tools/pack.py
