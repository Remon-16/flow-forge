"""Tests for converter.field_mapping — convert_row_to_snake.

重点验证 inherit 字段被解析为原生 dict（而非 JSON 字符串），
以保证 excel2yaml 输出的 YAML 里 inherit 是原生映射、执行器可解析。
Focus: inherit must be parsed into a native dict (not a JSON string) so that
excel2yaml emits a native YAML mapping the executor can resolve.
"""

from converter.field_mapping import convert_row_to_snake


class TestConvertRowToSnakeInherit:

    def should_parse_inherit_json_string_to_dict(self):
        row = {"Inherit": '{"authToken": "Step_Login.data.token"}'}
        result = convert_row_to_snake(row, parse_json=True)
        assert result["inherit"] == {"authToken": "Step_Login.data.token"}
        assert isinstance(result["inherit"], dict)

    def should_parse_inherit_multi_key_json(self):
        row = {"Inherit": '{"a": "S1.x", "b": "S2.y"}'}
        result = convert_row_to_snake(row, parse_json=True)
        assert result["inherit"] == {"a": "S1.x", "b": "S2.y"}

    def should_keep_inherit_string_when_invalid_json(self):
        # 非法 JSON 应回退保留原字符串，不抛异常
        # Invalid JSON should fall back to the raw string without raising
        row = {"Inherit": "not-valid-json"}
        result = convert_row_to_snake(row, parse_json=True)
        assert result["inherit"] == "not-valid-json"

    def should_not_parse_inherit_when_parse_json_disabled(self):
        row = {"Inherit": '{"authToken": "Step_Login.data.token"}'}
        result = convert_row_to_snake(row, parse_json=False)
        assert result["inherit"] == '{"authToken": "Step_Login.data.token"}'


class TestConvertRowToSnakeOtherFields:

    def should_parse_request_head_json_like_inherit(self):
        # 对照：既有 JSON 字段 RequestHead 行为应与 inherit 一致
        # Control: existing JSON field RequestHead should behave like inherit
        row = {"RequestHead": '{"Authorization": "Bearer #{authToken}"}'}
        result = convert_row_to_snake(row, parse_json=True)
        assert result["request_head"] == {"Authorization": "Bearer #{authToken}"}

    def should_convert_pascal_keys_to_snake(self):
        row = {"StepID": "Step_Login", "AppName": "foliMail", "Method": "POST"}
        result = convert_row_to_snake(row, parse_json=True)
        assert result["step_id"] == "Step_Login"
        assert result["app_name"] == "foliMail"
        assert result["method"] == "POST"

    def should_skip_empty_values(self):
        row = {"StepID": "S1", "Remark": "", "Tag": None}
        result = convert_row_to_snake(row, parse_json=True)
        assert result == {"step_id": "S1"}
