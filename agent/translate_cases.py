#!/usr/bin/env python3
"""Flow Forge — 测试用例字段翻译工具 / Test Case Field Translation Tool.

独立的 CLI 兜底工具。在用例生成后第一时间运行翻译，然后再进行人工修改。
Standalone CLI safety-net tool. Run translation immediately after case generation,
before manual editing.

Usage:
    python translate_cases.py output/cases/ --target-lang zh_CN
    python translate_cases.py output/cases/ -o translated/ --dry-run
"""

import os
import sys

# 注入 shared/py 到 sys.path，使 flow_forge_schemas 可导入
# Inject shared/py onto sys.path so flow_forge_schemas is importable
_SHARED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from cli.translate import translate_main

if __name__ == "__main__":
    sys.exit(translate_main())
