#!/usr/bin/env python3
"""Flow Forge — API Test Case Generation Agent CLI.

Usage:
    python main.py --requirement docs/req.md --api docs/api.yaml
    python main.py --requirement docs/req.md --api docs/api.yaml --output my_output
    python main.py --requirement docs/req.md --api docs/api.md --parse-mode llm
    python main.py --resume --output output_20240101_120000

See README.md for full documentation.
"""

import os
import sys

# 注入 shared 包路径 — 使 flow_forge_schemas 可导入
# Inject shared package path — makes flow_forge_schemas importable
_SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from cli import main

if __name__ == "__main__":
    sys.exit(main())
