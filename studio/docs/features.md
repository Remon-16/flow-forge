# 功能详解

[← 返回 studio/README](../README.md)

Flow Forge Studio 提供三个工作区：Excel 编辑器、YAML 编辑器、Markdown 计划批注器。本文档详解各工作区功能、查找替换与快捷键。

---

## 通用功能

- 首页编辑器选择（Excel / YAML / Markdown 计划批注器）
- Tauri 桌面应用，本地文件保存回原路径
- 中英文双语界面，可随时切换
- 保存（Ctrl+S）与另存为（Ctrl+Alt+S）
- **查找与替换**（Ctrl+F / Ctrl+H）：Excel 中按表格单元格查找，YAML 中按原始文本查找，支持大小写、全词匹配、正则表达式
- **「编辑」菜单**：工具栏「编辑」下拉提供「查找」「替换」「在文件中查找」「在文件中替换」，以及「放大」「缩小」「重置缩放」
- **字体缩放**：Ctrl+= 放大 / Ctrl+- 缩小 / Ctrl+0 重置 / Ctrl+鼠标滚轮缩放，缩放比例持久化
- **全局搜索**：「在文件中查找」跨所有 Sheet（Excel）或项目目录所有 YAML 文件搜索，结果按来源分组；「在文件中替换」支持逐条审查替换和全部替换

---

## Excel 编辑器

### 打开与保存

- 打开：工具栏「打开」按钮或 Ctrl+O，选择 `.xlsx` 文件（桌面模式直接读取本地文件并记录路径）
- 保存（Ctrl+S）：写回原始文件路径
- 另存为（Ctrl+Alt+S）：弹出保存对话框选择新路径

### 编辑功能

- 接口定义页编辑（表格形式，支持新增/删除行）
- 单接口测试用例编辑（RelevanceID 关联校验）
- 业务链路用例编辑（StepID 重复校验、Inherit 字段格式校验）
- 各列编辑方式：普通文本直接输入；Method 下拉选择；RequestHead / RequestBody / AssertDict 点击弹出 JSON 编辑器；AssertRules 只读预览 + 「编辑详情」结构化弹窗；PreProcessors / PostProcessors 为 JSON 数组列
- 实时校验（RelevanceID 存在性、StepID 唯一性、Inherit 格式），校验失败标红

### JSON 可视化编辑器

将 RequestHead、RequestBody、AssertDict 等 JSON 字段转为交互式树形编辑器：

- 粘贴 JSON 字符串自动解析
- 每字段展示 key / type / value 三列，均可编辑
- 支持 6 种类型：字符串、数字、布尔、日期、列表、字典
- 支持嵌套 Dict/List 递归编辑

### 高级断言编辑器（AssertRules）

- 逐条规则编辑，实时格式校验
- 每条规则分为路径、运算符、期望值三列独立编辑
- 支持「批量粘贴」：一次粘贴多行规则，自动拆分解析
- 运算符与函数完整参考见 [校验规则与断言参考](./validation.md#assertrules-运算符与函数参考)

---

## YAML 编辑器

### 打开用例

- **打开目录**：头部「打开」→「打开目录」，选择含 `.yaml` 的目录，左侧显示文件树（VS Code 风格）
- **打开文件**：头部「打开」→「打开文件」，直接选择单个 `.yaml`
- **文件标签页**：同时打开多个文件，标签页切换，点击 × 关闭

### 表单编辑

根据 `case_type` 字段自动切换表单类型：

- `single`：单接口用例表单（test_id、relevance_id、api_name、method、url 等）
- `biz`：业务链路表单（sheet_name + 步骤列表，可拖拽排序）
- `interfaces`：接口定义表单（不含 relevance_id 和 tag）

简单字段以两列网格布局呈现；JSON 字段（RequestHead/RequestBody/AssertDict）、AssertRules、PreProcessors/PostProcessors、备注独占一行。JSON 与 AssertRules 可直接在文本框编辑（失焦自动保存），也可点「编辑详情」打开结构化编辑器。复用 Excel 编辑器的 JSON 编辑器和 AssertRules 编辑器。

### YAML 预览面板

右侧面板可切换：

- 折叠状态：只显示切换按钮
- 编辑模式（默认）：直接编辑 YAML 文本，输入半秒后自动解析更新表单，适合大批量复制粘贴
- 预览模式：实时显示当前表单序列化后的 YAML（只读）

### 右键菜单文件操作

在文件树中右键文件或文件夹：重命名、剪切、复制、粘贴、删除至回收站、在文件资源管理器中打开。

保存与另存为同 Excel 编辑器（Ctrl+S / Ctrl+Alt+S）。

---

## Markdown 计划批注器

用于对 AI 生成的测试计划（`plan.md`）添加结构化批注，供智能体在审核环节（输入 `r`）读取修改计划。

### 打开与添加批注

1. 首页点击「Markdown 计划批注器」卡片，通过「打开目录」选择含 Markdown 计划的目录，左侧文件树选择文件
2. 在渲染后的 Markdown 预览中选中需批注的文本
3. 右键选择「添加批注」，输入评审意见
4. 批注记录格式：行号、选中文本、评审意见
5. 被批注文字以黄色高亮显示，右下角带浅蓝色编号标签

### 管理批注

- **点击批注高亮**：弹出详情气泡，显示批注内容、行号，可直接编辑或删除
- 左侧批注列表显示当前文件所有批注，支持编辑、删除、滚动定位
- 删除批注后，高亮和标签同步取消

### 自动保存与历史批注

- 所有批注自动保存到计划目录下的 `plan_comments.json`，无需手动保存
- 切换「历史批注」模式可查看之前保存的所有批注记录（只读），便于回溯评审历史

### 与 AI 智能体集成

批注数据供 [AI 用例生成智能体](../../agent/README.md) 使用。在 CLI 审核环节选择 `r` 时，智能体读取 `plan_comments.json` 中的批注，作为修改测试计划的上下文参考。

---

## 处理器编辑

PreProcessors / PostProcessors 列支持三种编辑方式：

- **内联编辑** — 直接在单元格编辑 JSON 文本
- **JSON 树编辑器** — 点「详情」打开树形编辑器
- **列表编辑器** — 名称 + key=value 配置列表界面，支持增删改、排序、JSON 粘贴

校验规则见 [校验规则与断言参考](./validation.md#处理器字段校验)。

---

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 打开文件 |
| Ctrl+S | 保存 |
| Ctrl+Alt+S | 另存为 |
| Ctrl+N | 新建空白工作簿 |
| Ctrl+F | 查找 |
| Ctrl+H | 替换 |
| Ctrl+= | 放大字体 |
| Ctrl+- | 缩小字体 |
| Ctrl+0 | 重置缩放 |
| Ctrl+鼠标滚轮 | 缩放字体 |
| Esc | 关闭查找栏 |
