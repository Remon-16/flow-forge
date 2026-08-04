# flowforge-testing — Flow Forge 强模型 Agent Skill

**中文** | [English](README.en.md)

把 Flow Forge 的用例生成工作流提炼成一份可供 Codex / opencode / Claude Code 等 ReAct 智能体装载的 skill：多文档分析 → plan（可选）→ YAML 用例生成 → schema 校验 → 执行器运行 → 错误分诊 → 修改/报告。

## 为什么单独做这个 skill

`agent/` 流水线是为弱模型设计的（英文提示词、文档分块、上下文压缩、人工审核）。强模型直接走流水线会浪费 token。本 skill 让强模型用自己的 ReAct 能力按同一套质量标准完成工作，只在需要确定性时调用 `python/` 执行器与转换器。

## 功能

- **生成模式**：需求/接口文档（可多份）+ 表结构/业务规则 → plan（默认）→ YAML 用例。
- **修改模式**：需求/接口变更 + 现有用例 → 差异分析 → 增改删 → 校验执行。
- **校验**：`ff_tool validate` 按 `shared/schemas` 静态校验（必填字段、断言、inherit、处理器配置）。
- **执行与分诊**：调用 `python/` 执行器，区分"用例错 / 业务 bug / 环境问题"。
- **转换**：YAML ↔ Excel（按需）。
- **两种模式**：plan（默认，先出计划确认）/ auto（无人值守直接跑）。
- **中间件**：数据库/Redis/MQ 前置与后置处理按通用处理器机制接入，不绑定具体业务。

## 目录结构

```text
flowforge-testing/
├── SKILL.md                      # 智能体指令（英文），入口文件
├── README.md / README.en.md      # 本说明文档
├── flowforge.config.yaml.example # 配置模板
├── scripts/
│   ├── resolve_python.py         # 按配置解析 Python 解释器
│   ├── ff_tool.py                # validate / execute / convert 统一入口
│   ├── i18n/                     # 日志国际化（zh_CN / en_US）
│   └── tests/                    # 脚本测试（零 LLM 调用）
└── references/
    └── PLAN_TEMPLATE.md          # plan 输出结构模板
```

## 快速开始

```bash
# 1) 复制配置模板并填写 / Copy the config template and fill it in
cp flowforge.config.yaml.example flowforge.config.yaml
```

```yaml
# 关键配置项 / Key settings
language: zh_CN        # 输出语言 / output language
mode: plan             # plan | auto
python:
  mode: auto           # auto | conda | venv | system
  conda_env: api_test  # 例如 / e.g. api_test
```

把本目录接入你的智能体（见下），然后让智能体读取 `SKILL.md` 并开始工作即可。

## 接入不同智能体

### Codex

- 复制或软链到 `~/.codex/skills/flowforge-testing`（推荐，可自动发现）；
- 或在会话中直接指定：`使用 <flow-forge 仓库根目录>/flowforge-testing 的 skill 生成测试用例`。

### Claude Code

- 复制到项目 `.claude/skills/flowforge-testing/`，或用 `--add-dir` 指向本目录。

### opencode

- 在 `AGENTS.md` 中引用本目录的 `SKILL.md`，或将目录复制到项目 `skills/` 下。

> skill 本体（SKILL.md + scripts + references）是通用的，各平台仅接入方式不同，细节以平台官方文档为准。

## 与 agent/ 弱模型流水线的关系

| 场景 | 推荐路径 |
|------|----------|
| 强模型（GPT/Claude/DeepSeek 等） | 本 skill + ReAct 智能体 |
| 弱模型（llama.cpp/Ollama 等） | `agent/` 的 LangGraph 流水线 |
| 弱模型初版 + 强模型修订 | 弱模型出初版用例 → 本 skill 的 modify 模式修订 |

## 拷贝到其他仓库

本 skill 依赖 flow-forge 仓库布局（`python/`、`shared/`）。拷贝到其他仓库时：

- 保持 `flowforge.config.yaml` 的 `flowforge_root` 指向仓库根目录；
- 确认 `python/` 与 `shared/` 存在，否则按需调整 `scripts/` 中的路径。

## 开发与测试

所有测试在 api_test conda 环境中执行，无 LLM 调用、无真实网络请求：

```bash
conda activate api_test
python -m pytest flowforge-testing/scripts/tests -v
```
