#!/usr/bin/env bash
# Wait for harvest_metadata.py to finish, then rebuild the SQLite index.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    echo "[env] using active virtualenv: ${VIRTUAL_ENV}"
fi

echo "[wait] watching for harvest to complete..."
while pgrep -f "python harvest_metadata.py" >/dev/null 2>&1; do
    n=$(python - <<'PY'
from pathlib import Path
print(sum(1 for _ in Path("data/sourcedetails").glob("*.json")))
PY
)
    echo "[wait] harvest running... sourcedetails=$n files"
    sleep 120
done

echo "[build] harvest finished — rebuilding index"
python build_index.py --src data/sourcedetails --catalogue data/catalogue.csv
python -c "
import sqlite3
from schema import INDEX_DB_PATH
c = sqlite3.connect(INDEX_DB_PATH)
print('[build] datasets:', c.execute('select count(*) from datasets').fetchone()[0])
print('[build] indicators:', c.execute('select count(*) from indicators').fetchone()[0])
print('[build] dimensions:', c.execute('select count(*) from dimensions').fetchone()[0])
"
if [[ -f data/catalogue.csv ]]; then
    python scripts/check_index_coverage.py
fi
echo "[done] index ready at data/index.db"
