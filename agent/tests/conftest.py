"""pytest configuration — inject shared/py into sys.path for all tests."""
import os
import sys
from pathlib import Path

# 注入 shared/py 到 sys.path，使 flow_forge_schemas 模块可导入
# Inject shared/py onto sys.path so flow_forge_schemas is importable
_AGENT_DIR = Path(__file__).resolve().parent.parent
_SHARED = os.path.normpath(os.path.join(str(_AGENT_DIR), "..", "shared", "py"))
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))
