"""Public CLI, runnable as a module or by absolute script path."""

import sys
from io import TextIOWrapper
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.manager import main

if __name__ == "__main__":
    cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
    cast(TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8")
    raise SystemExit(main())
