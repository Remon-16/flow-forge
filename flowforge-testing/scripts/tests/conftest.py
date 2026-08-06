"""pytest 配置 — 注入 scripts 与 shared/py 到 sys.path。

pytest config: inject the scripts dir and shared/py onto sys.path.
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_SHARED = Path(__file__).resolve().parents[3] / "shared" / "py"

for _p in (_SCRIPTS, _SHARED):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
