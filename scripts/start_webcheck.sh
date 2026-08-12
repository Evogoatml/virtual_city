#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.hermes/node/bin:${PATH}"
python3.13 - <<'PY'
from buildings.web_check.service import start, status
import json
print(json.dumps(start(), indent=2))
print("---")
print(json.dumps(status(), indent=2))
PY
