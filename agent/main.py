#!/usr/bin/env python3
"""Flow Forge — API Test Case Generation Agent CLI.

Usage:
    python main.py --requirement docs/req.md --api docs/api.yaml
    python main.py --requirement docs/req.md --api docs/api.yaml --output my_output
    python main.py --requirement docs/req.md --api docs/api.md --parse-mode llm
    python main.py --resume --output output_20240101_120000

See README.md for full documentation.
"""

import sys

from cli import main

if __name__ == "__main__":
    sys.exit(main())
