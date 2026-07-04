# 读取 shared/schemas/ 下的 JSON 数据文件，构造 Python 原生对象。
# Load JSON data files from shared/schemas/ and construct Python native objects.
import json
from pathlib import Path

# JSON 数据目录 — shared/schemas/
# JSON data directory — shared/schemas/
_SCHEMAS = Path(__file__).parent.parent.parent / "schemas"


def _load(name: str):
    """加载 JSON 数据文件。 / Load a JSON data file."""
    with open(_SCHEMAS / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Excel 列头定义 / Excel column definitions
# ============================================================================
_cols = _load("columns")

# 接口定义列（13 列） / Interface definition columns (13 columns)
API_COLUMNS: list[str] = _cols["api"]

# 单接口用例列（15 列） / Single case columns (15 columns)
CASE_COLUMNS: list[str] = _cols["case"]

# 业务链路步骤列（16 列） / Biz flow step columns (16 columns)
BIZ_COLUMNS: list[str] = _cols["biz"]


# ============================================================================
# 字段名映射 / Field name mapping
# ============================================================================
_fm = _load("field-mapping")

# snake_case → PascalCase
SNAKE_TO_PASCAL: dict[str, str] = _fm["snake_to_pascal"]

# PascalCase → snake_case
PASCAL_TO_SNAKE: dict[str, str] = {v: k for k, v in _fm["snake_to_pascal"].items()}

# JSON 列字段 — 在 Excel 中存为 JSON 字符串，在内存中为 dict/list
# JSON column fields — stored as JSON strings in Excel, dict/list in memory
JSON_FIELDS: frozenset[str] = frozenset(_fm["json_fields"])


# ============================================================================
# 校验常量 / Validation constants
# ============================================================================
_c = _load("constants")

# 合法 HTTP 方法 / Valid HTTP methods
VALID_HTTP_METHODS: frozenset[str] = frozenset(_c["http_methods"])

# 合法 Tag 等级 / Valid tag levels (strict, 仅 P0-P3)
VALID_TAGS: frozenset[str] = frozenset(_c["valid_tags"])

# Tag 等级列表（含 P4，用于编辑器下拉） / Tag level list (includes P4, for editor dropdown)
TAG_LEVELS: list[str] = _c["tag_levels"]

# 单接口用例必填字段 / Required fields for single test case
REQUIRED_SINGLE: list[str] = _c["required_single"]

# 业务链路步骤必填字段 / Required fields for biz flow step
REQUIRED_BIZ_STEP: list[str] = _c["required_biz_step"]

# 业务链路必填字段 / Required fields for biz flow
REQUIRED_BIZ_FLOW: list[str] = _c["required_biz_flow"]

# URL 不存在前缀标记 / URL-not-exist prefix marker
URL_NOT_EXIST_PREFIX: str = _c["url_not_exist_prefix"]


# ============================================================================
# 断言规则运算符 / Assertion rule operators
# ============================================================================
_ops = _load("operators")

# 运算符列表（按优先级排序） / Operator list (priority-ordered)
OPERATOR_LIST: list[dict] = _ops["operators"]

# 合法函数 / Valid functions in assertion expressions
VALID_FUNCTIONS: frozenset[str] = frozenset(_ops["valid_functions"])

# typeof 合法类型 / Valid types for typeof operator
VALID_TYPES: frozenset[str] = frozenset(_ops["valid_types"])


# ============================================================================
# 便捷函数 / Convenience functions
# ============================================================================

def snake_to_pascal(name: str) -> str:
    """snake_case → PascalCase 转换。 / Convert snake_case to PascalCase."""
    return SNAKE_TO_PASCAL.get(name, name)


def pascal_to_snake(name: str) -> str:
    """PascalCase → snake_case 转换。 / Convert PascalCase to snake_case."""
    return PASCAL_TO_SNAKE.get(name, name)
