#!/data/data/com.termux/files/usr/bin/bash
set -u

echo
echo "================================"
echo "       GaweYuk DEV CHECK"
echo "================================"

FAIL=0

echo
echo "[1/4] Pipeline..."
if python -m pytest tests/test_ingestion_pipeline*.py -q; then
  echo "Pipeline       PASS"
else
  echo "Pipeline       FAIL"
  FAIL=1
fi

echo
echo "[2/4] ATS connectors..."
if python -m pytest \
  tests/test_collector_identity.py \
  tests/test_collectors_greenhouse.py \
  tests/test_collectors_lever.py \
  tests/test_collectors_ashby.py \
  -q; then
  echo "ATS Connectors PASS"
else
  echo "ATS Connectors FAIL"
  FAIL=1
fi

echo
echo "[3/4] Full regression..."
if python -m pytest -q; then
  echo "Regression     PASS"
else
  echo "Regression     FAIL"
  FAIL=1
fi

echo
echo "[4/4] Git quality..."
if git diff --check && git diff --cached --check; then
  echo "Git Diff       CLEAN"
else
  echo "Git Diff       FAIL"
  FAIL=1
fi

echo
echo "================================"

if [ "$FAIL" -eq 0 ]; then
  echo "GAWEYUK STATUS: READY NEXT ✅"
  echo "Tests: $(python -m pytest -q 2>/dev/null | tail -1)"
else
  echo "GAWEYUK STATUS: FAILED ❌"
  echo "Kirim 15-20 baris error terakhir saja."
fi

echo "================================"
