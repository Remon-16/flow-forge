"""Excel 列头定义 — excel_reader 和 excel_writer 共享。
   Excel column header definitions — shared by excel_reader and excel_writer."""

# 接口定义列（13 列）
# Interface definition columns (13 columns)
API_COLUMNS = [
    "TestID", "APIName", "AppName", "Method", "URL",
    "RequestHead", "RequestBody", "StatusCode", "AssertDict", "AssertRules",
    "PreProcessors", "PostProcessors", "Remark",
]

# 单接口用例列（15 列）
# Single case columns (15 columns)
CASE_COLUMNS = [
    "TestID", "RelevanceID", "Tag",
    "APIName", "AppName", "Method", "URL",
    "RequestHead", "RequestBody", "StatusCode", "AssertDict", "AssertRules",
    "PreProcessors", "PostProcessors", "Remark",
]

# 业务链路步骤列（16 列）
# Business flow step columns (16 columns)
BIZ_COLUMNS = [
    "StepID", "RelevanceID", "Inherit",
    "APIName", "AppName", "Method", "URL",
    "RequestHead", "RequestBody", "StatusCode", "AssertDict", "AssertRules",
    "PreProcessors", "PostProcessors", "Tag", "Remark",
]
