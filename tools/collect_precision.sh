set -eu
[ ! -e /repo/.phase5/precision ] || { echo 'move the existing precision traces before collecting again' >&2; exit 1; }
mkdir -p /src /tmp/precision/0 /tmp/precision/1
tar xf /repo/.phase5/src.tar -C /src
cd /src
export PYTHONPATH=/repo/tools:/repo:/src SKIP_INTEGRATION=0 OPENBLAS_NUM_THREADS=1
python -c 'import sys, pytest; assert sys.version_info[:3] == (3, 13, 18) and pytest.__version__ == "9.2.0"'
python -m compileall -q sqlglot tests
python /repo/tools/precision_plan.py /src > /tmp/precision/plan.json
for order in 0 1; do
    status=0
    PYTHONHASHSEED="$((100 + order))" BR_PRECISION=1 BR_REVERSE="$order" python -m pytest -q -p trace_plugin tests > "/repo/.phase5/precision-order-$order.log" 2>&1 || status=$?
    [ "$status" -le "$order" ] || exit "$status"
    cp /tmp/collected.json /tmp/precision/"$order"/collected
    cp /tmp/pass"$order".json /tmp/precision/"$order"/outcomes
done
cp -r /tmp/precision /repo/.phase5/
