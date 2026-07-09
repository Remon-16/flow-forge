# 注入 shared 包路径 — 使 flow_forge_schemas 在测试中可导入。
# Inject shared package path — makes flow_forge_schemas importable during tests.
import os
import sys

_SHARED = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "shared", "py")
)
if os.path.isdir(_SHARED) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)
