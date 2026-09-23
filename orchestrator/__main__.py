"""Allow `python -m orchestrator` as well as `python -m orchestrator.cli`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
