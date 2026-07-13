# 配置与命令行参考

[← 返回 agent/README](../README.md)

本文档覆盖智能体的完整配置项（`env.yaml`）、翻译工具配置（`translate_env.yaml`）以及全部命令行参数。

---

## env.yaml — 主配置文件

智能体使用 `env.yaml`（YAML 格式）作为统一配置。通过复制模板创建：

```bash
cp env.example.yaml env.yaml
# 编辑 env.yaml 并填入配置
```

`env.example.yaml` 带完整双语注释，是配置项的权威来源。下面按段说明。

### llm — LLM 供应商配置

```yaml
llm:
  provider: openai        # 仅支持 openai（见下方说明）
  api_key: sk-...         # API 密钥（必填）
  model: gpt-4o           # 模型名称
  temperature: 0.3        # 生成温度 0.0~2.0
  max_output_tokens: 4096 # 单次最大输出 token
  context_window: 128000  # 上下文窗口大小（token）
  context_compression_threshold: 0.9  # 上下文压缩阈值（推理模型建议 0.95，小窗口模型 0.8）
  base_url: ""            # API Base URL；OpenAI 官方留空，第三方填写
  max_concurrency: 1      # 最大并发请求数（0=无限制）
  rate_limit_delay: 0.0   # 请求最小间隔秒数
  retry_base_delay: 2.0   # 重试基础延迟秒数
  request_timeout: 600.0  # HTTP 请求超时秒数（连接 + 读取）
  extra_params: {}        # 额外 API 参数（如思考模式，见下）
```

> **只支持 OpenAI 兼容 API**：`provider` 目前仅实现 `openai`（`llm/factory.py` 使用 `langchain_openai.ChatOpenAI`）。任何提供 OpenAI 兼容端点的服务都可通过设置 `base_url` 接入：
> - **DeepSeek**：`base_url: "https://api.deepseek.com"`，`model: deepseek-v4-flash`
> - **Ollama（本地）**：`base_url: "http://<host>:11434/v1"`，`model: qwen2.5-coder:14b-instruct-q6_K`
> - **OpenAI 官方**：`base_url` 留空

#### 思考模式（Thinking Mode）

通过 `llm.extra_params` 配置厂商特定的思考/推理参数，参数以 `**kwargs` 形式原样传递给 OpenAI SDK 的 `chat.completions.create()`：

```yaml
# DeepSeek 思考模式
llm:
  extra_params:
    reasoning_effort: "high"
    extra_body: {"thinking": {"type": "enabled"}}

# OpenAI o-series 推理强度
llm:
  extra_params:
    reasoning_effort: medium
```

> 参数名和值取决于具体模型/API 厂商，配置前请查阅对应厂商文档。不支持的参数可能被忽略或报错。

### pipeline — 流水线设置

```yaml
pipeline:
  max_steps: 10                      # 最大智能体步数
  max_retries: 3                     # LLM 调用最大重试次数
  max_steps_no_progress: 5           # 进度无变化最大步数
  consecutive_batch_failure_limit: 3 # 连续批次失败上限（-1=永不停止）
  skeleton_batch_size: 30            # 骨架生成分批大小（每批测试点数）
  plan_single_batch_size: 8          # 单接口测试点分组大小（-1=不拆分，强模型建议 -1）
  case_type: both                    # 用例生成类型：both | single | biz
  plugin_batch_size: 10              # 插件处理批次大小（-1=不分批）
  auto: false                        # 自动模式：跳过人工审核（夜间批量生成建议开启）
```

#### 用例类型选择（case_type）

| 值 | 说明 |
|----|------|
| `both` | 同时生成单接口用例和业务链路用例（默认） |
| `single` | 仅生成单接口用例，跳过业务链路阶段 |
| `biz` | 仅生成业务链路用例，跳过单接口阶段 |

跳过逻辑在代码级别执行，不影响轮廓生成——轮廓仍包含完整的 `api_groups` 和 `biz_flows`。也可用 `--case-type` CLI 参数覆盖。

### knowledge — 知识库

> 目前知识库属于Beta内容

```yaml
knowledge:
  enabled: false     # 启用知识库（基于 grep 的纯文本检索）
  dir: ./knowledge   # 知识库目录
```

详见 [how-it-works.md 的知识库章节](./how-it-works.md#知识库)。

### validation — 校验与纠错

```yaml
validation:
  # ··· 用例格式校验 / Case format validation ···
  case_format_enabled: true            # 启用用例格式校验（原名 enabled）
  case_format_max_retries: 3           # 用例格式校验重试次数

  # ··· URL 文档匹配纠错 / URL doc-match correction ···
  url_doc_match_rules:
    max_retries: 3                     # URL 纠错重试次数（原 url_doc_match_max_retries）
    strategy: warn                     # 纠错耗尽后策略: fail | warn | skip

  # ··· 用例生成阶段校验规则 / Case generation validation rules ···
  case_gen_rules:
    - check: skeleton_count
      strategy: warn
    - check: url_check
      strategy: warn
      failure_action: keep   # 仅 url_check：discard（丢弃到 failures.yaml）| keep（保留继续插件处理）
    - check: data_fill_count
      strategy: warn
    - check: assertion_count
      strategy: warn
```

**策略值**：`fail`（终止并重试）| `warn`（警告继续）| `skip`（跳过）。

**两种 YAML 写法均支持**（`config/settings.py` 的 `_parse_validation_rules`）：

```yaml
# 列表格式
case_gen_rules:
  - check: url_check
    strategy: warn
    failure_action: keep

# 字典格式（简写）
case_gen_rules:
  skeleton_count: fail
  url_check: warn

# 字典格式（嵌套，可带 failure_action）
case_gen_rules:
  url_check:
    strategy: warn
    failure_action: keep
```

> **代码默认值 vs 示例**：不配置 `case_gen_rules` 时，代码默认 `skeleton_count` / `data_fill_count` / `assertion_count` 为 `fail`、`url_check` 为 `warn`（`settings.py`）。`env.example.yaml` 中演示为全部 `warn`，仅作演示，实际以你配置或代码默认为准。

关于各校验项与 URL 纠错的详细行为，见 [anti-hallucination.md](./anti-hallucination.md)。

### output — 输出设置

```yaml
output:
  dir: ./output      # 输出根目录
  format: both       # yaml | excel | both
```

### plugins / skills — 插件与技能

```yaml
plugins:
  enabled: true
  modules:
    - plugins.official.data_filling.DataFillingPlugin
    - plugins.official.assertion_generation.AssertionGenerationPlugin

skills:
  enabled: true
  agents:
    data_filler:
      - foli_mall_data_filling
    assertion_generator:
      - foli_mall_assertion
```

详见 [plugins-and-skills.md](./plugins-and-skills.md)。

### agent / logging

```yaml
agent:
  lang: zh_CN          # 界面语言：zh_CN | en_US

logging:
  log_to_output: false # 是否将日志持久化到 output_dir/logs/agent.log（默认关闭）
```

---

## 命令行参数

主入口 `python main.py`。完整参数（与 `cli/parser.py` 一致）：

| 参数 | 说明 |
|------|------|
| `--requirement PATH [PATH ...]` | 需求文档路径（`.txt` / `.md` / `.pdf`），可多个 |
| `--api PATH` | 接口文档路径（OpenAPI `.yaml`/`.json` 或 Markdown `.md`） |
| `--output PATH` | 输出根目录（默认 `./output_<timestamp>`） |
| `--output-format {yaml,excel,both}` | 输出格式（默认 `both`，留空时取自 `env.yaml`） |
| `--parse-mode {raw,rule,llm}`, `-m` | API 文档解析模式（默认 `raw`）：`raw`=LLM 分析原文，`rule`=规则解析器，`llm`=LLM 预提取 |
| `--parser-path PATH` | 自定义解析器 `.py` 路径（仅 `--parse-mode rule` 生效） |
| `--reference-dir PATH` | 增量更新参考目录 |
| `--prompt TEXT`, `-p` | 用户补充指导，注入到计划和用例生成提示词中 |
| `--resume` | 从已有 output 目录恢复执行 |
| `--resume-overwrite` | 恢复时覆盖已有输出 |
| `--auto` | 自动模式：跳过所有人工审核 |
| `--case-type {single,biz,both}` | 用例生成类型（默认 `both`） |
| `--plugin-batch-size N` | 覆盖 `pipeline.plugin_batch_size`（插件处理批次大小）；默认取自 `env.yaml`。注意：这是**插件批次**，非计划分块 |
| `--max-steps N` | 覆盖 `pipeline.max_steps`（最大智能体步数） |
| `--max-retries N` | 覆盖 `pipeline.max_retries`（LLM 调用最大重试次数） |
| `--max-steps-no-progress N` | 覆盖 `pipeline.max_steps_no_progress`（进度无变化最大步数） |
| `--consecutive-batch-failure-limit N` | 覆盖 `pipeline.consecutive_batch_failure_limit`（连续批次失败上限） |
| `--skeleton-batch-size N` | 覆盖 `pipeline.skeleton_batch_size`（骨架生成分批大小） |
| `--plan-single-batch-size N` | 覆盖 `pipeline.plan_single_batch_size`（单接口测试点分组大小） |
| `--url-doc-match-max-retries N` | 覆盖 `validation.url_doc_match_rules.max_retries`（URL 与文档原文匹配重试上限） |
| `--url-doc-match-strategy {fail,warn,skip}` | 覆盖 `validation.url_doc_match_rules.strategy`（URL 纠错耗尽后策略） |
| `--case-format-max-retries N` | 覆盖 `validation.case_format_max_retries`（用例格式校验重试次数） |
| `--validation` / `--no-validation` | 启用/禁用校验（覆盖 `validation.case_format_enabled`） |
| `--knowledge` / `--no-knowledge` | 启用/禁用知识库（覆盖 `knowledge.enabled`） |
| `--plugins` / `--no-plugins` | 启用/禁用插件（覆盖 `plugins.enabled`） |
| `--skills` / `--no-skills` | 启用/禁用技能（覆盖 `skills.enabled`） |
| `--lang {zh_CN,en_US}` | 覆盖 `agent.lang`（界面语言） |
| `--debug-snapshots` | 保存调试快照（`interfaces.json` + `extracted_texts.json`） |
| `--debug` | 启用调试日志（完整 LLM I/O 写入 session `debug.log`） |
| `--env PATH` | 配置文件路径（默认 `env.yaml`） |
| `-v`, `--verbose` | 启用详细控制台日志 |
| `--log-to-output` | 将日志持久化到输出目录（`{output_dir}/logs/agent.log`） |

命令示例见 [agent/README.md 快速开始](../README.md)；自动模式与断点续写见 [how-it-works.md](./how-it-works.md#自动模式auto-mode)。

### 断点续写时的配置行为 / Config Behavior on Resume

首次运行时，所有 CLI 参数和配置会自动保存到 `{output_dir}/memory/run_config.json`。恢复时：

- **默认行为**：使用已保存的配置作为默认值（对已完成的阶段保持不变）
- **CLI 覆盖**：`--resume` 时提供的 CLI 参数会覆盖已保存的配置，但仅对**尚未执行**的阶段生效
- **过期覆盖警告**：如果 CLI 覆盖影响到的阶段已经执行完毕，系统会发出 `[Resume] 警告` 日志提示用户当前覆盖可能无效

示例：计划已生成完毕后，`--resume` 时添加 `-p "新指导"` 不会影响已生成的计划，系统会提示该覆盖可能无效。

> 向后兼容：对于没有 `run_config.json` 的旧流水线，恢复时完全使用 CLI 参数（与之前行为一致）。

**配置保存范围**：`case_type`、`user_guidance`（对应 `-p`）、`output_format`、`plugin_batch_size`、`auto_mode`、`parse_mode`、`output_dir`、`api_path`、`requirement_paths`、`debug_snapshots`、`parser_path`、`reference_dir`。

---

## translate_cases.py — 用例字段翻译工具

当使用弱模型（如本地 Ollama 小参数量模型）生成用例时，`api_name` / `sheet_name` / `remark` 等字段可能出现中英文混合或全英文。翻译工具作为**兜底机制**，对已生成用例进行字段翻译。

> **使用时机**：建议在用例生成后**第一时间运行翻译**，再进行人工修改，避免手工调整被覆盖。

```bash
# 翻译整个输出目录下的所有用例
python translate_cases.py output/cases/ --target-lang zh_CN

# 翻译到指定输出目录（保留原始目录不变）
python translate_cases.py output/cases/ -o translated_cases/

# 预览模式（不写文件，仅查看哪些用例需要翻译）
python translate_cases.py output/cases/ --target-lang zh_CN --dry-run

# 禁用已翻译检测（全量翻译）
python translate_cases.py output/cases/ --no-detection
```

### 翻译工具参数

| 参数 | 说明 |
|------|------|
| `input_dir` | 用例目录路径（通常是 agent 的 `output/cases/`） |
| `--output`, `-o` | 输出根目录（默认 `<input_dir>_translated`） |
| `--config`, `-c` | 翻译配置文件（默认 `translate_env.yaml`） |
| `--target-lang` | 目标语言：`zh_CN` 或 `en_US` |
| `--batch-size` | 每批最大用例数（覆盖配置文件） |
| `--no-detection` | 禁用已翻译检测 |
| `--dry-run` | 预览模式，不写入文件 |
| `--log-to-output` | 将日志持久化到输出目录 |
| `-v`, `--verbose` | 详细控制台日志 |

### 翻译策略

- **场景推断**：参考用例的 method、URL 等字段推断测试场景，生成符合业务语义的自然翻译（如 `DELETE /api/cart` → "删除购物车"，而非逐词翻译）。
- **字段保护**：只修改 `api_name` / `sheet_name` / `remark`，其他字段（`test_id`、`method`、URL 等）严格不变。
- **已翻译检测**：默认跳过已是目标语言的用例（可配置 `detection.enabled`）。
- **输入优先级**：目录下存在 YAML 时优先翻译 YAML；仅当无 YAML 时才读 Excel。若输入含 Excel 且用 YAML 翻译，输出时也会同步导出一份 Excel。

### 独立配置文件

翻译工具使用独立的 `translate_env.yaml`（模板 `translate_env.example.yaml`），与主流水线的 `env.yaml` 完全独立。可为翻译任务配置不同的 LLM（例如主流水线用本地弱模型，翻译用云端强模型）。

```bash
cp translate_env.example.yaml translate_env.yaml
# 编辑并填入翻译专用 LLM 配置
```
