"""Export the API contract without starting a service or initializing its data."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.main import app  # noqa: E402

if __name__ == "__main__":
    document = json.dumps(app.openapi(), ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(document)
