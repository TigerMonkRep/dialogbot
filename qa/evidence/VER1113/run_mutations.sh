#!/bin/bash
# Baseline (no mutation) then each mutation: run its tests on qa_v1113_mut; KILLED = tests fail with the mutation.
WT=/home/claude/ver1113/wt-mut; SPEC=/home/claude/ver1113/scripts/mutations.json; OUT=/home/claude/ver1113/logs/mutations
mkdir -p $OUT; S=/home/claude/ver1113/scripts/pytest-ci.sh
cd $WT; git checkout -q -- .
for g in H M E W; do
  case $g in H) T="tests/test_support.py tests/qa/test_qa_H01.py";; M) T="tests/test_ops_m03.py tests/qa/test_qa_M03.py";;
    E) T="tests/test_booking_messages.py tests/qa/test_qa_integ_E07.py";; W) T="tests/qa/test_qa_w04_w09_w13.py";; esac
  $S $WT qa_v1113_mut pytest -q -p no:cacheprovider $T > $OUT/baseline-$g.log 2>&1; echo "BASELINE $g exit=$? $(tail -1 $OUT/baseline-$g.log)"
done
for n in ${@:-$(python3 -c "import json;print(' '.join(json.load(open('$SPEC'))))")}; do
  python3 -I /home/claude/ver1113/scripts/mutate.py $WT $SPEC $n >/dev/null || { echo "$n APPLY-ERROR"; git checkout -q -- .; continue; }
  T=$(python3 -c "import json;print(' '.join(json.load(open('$SPEC'))['$n']['tests']))")
  $S $WT qa_v1113_mut pytest -q -p no:cacheprovider -x $T > $OUT/$n.log 2>&1; rc=$?
  git checkout -q -- .
  failed=$(grep -m1 -oE "^(FAILED|ERROR) [^ ]+" $OUT/$n.log | head -1)
  if [ $rc -ne 0 ]; then echo "$n KILLED rc=$rc $failed"; else echo "$n SURVIVED $(tail -1 $OUT/$n.log)"; fi
done
