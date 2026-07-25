# 反幻觉与错误处理

[← 返回 agent/README](../README.md)

LLM 难免产生幻觉（编造接口、URL、数量对不上等）。智能体在多个环节内建校验与纠错机制，尽量把不可靠输出拦在生成阶段。核心原则：**能纠正则纠正，纠正不了则明确标记，绝不静默放行**。

---

## 纯文本模态限制

智能体仅支持文本输入。PDF 中的图片/扫描件内容不会被提取，请提供文本层可提取的 PDF 或纯文本文档。传入二进制文件（如 `.png`、`.jpg`）会明确报错，而非静默产出空结果。

---

## LLM 输出数量校验（反幻觉）

骨架生成、数据填充、断言生成和 URL 纠错后，自动校验 LLM 输出条目数与输入是否一致。数量不匹配时自动重试（利用 `temperature > 0` 产生不同输出）。

每个校验项在 `validation.case_gen_validation.rules` 中支持三级策略：

| 策略 | 行为 |
|------|------|
| `fail` | 终止并重试 |
| `warn` | 警告并继续 |
| `skip` | 跳过校验 |

校验项：

| check | 含义 |
|-------|------|
| `skeleton_count` | 骨架数量校验 |
| `data_fill_count` | 数据填充数量校验 |
| `assertion_count` | 断言生成数量校验 |
| `url_check` | URL 存在性校验（见下） |
| `flow_match` | 流程关联校验（计划解析阶段，见下） |

配置写法（列表/字典两种格式）与代码默认值详见 [configuration.md 的 validation 段](./configuration.md#validation--用例校验)。

### 骨架分批与计划分块

- **骨架分批**：骨架生成默认每批 30 个测试点（`skeleton_batch_size`），测试点超过分批大小时自动拆分为多批，每批独立调用 LLM 后合并，提高大批量下的计数精度。
- **计划分块**：测试计划采用"轮廓 + 四阶段"法——先生成轻量 JSON 轮廓（< 1000 token，确保不被截断），再分四阶段生成：A) 全局业务理解 + 流程图 → B) 按 `plan_single_batch_size` 分组的单接口测试点 → C) 业务链路测试（`plan_biz_flow_batch_size` 作为代码级保留常量，非用户可配） → D) 拼接。每个分块独立调用 LLM 并重置步数计数器，防止单次调用耗尽 `max_steps`。`plan_single_batch_size` 支持 `-1`（不拆分），强模型可设 `-1` 加快执行。

---

## URL 纠错

接口 URL 是最容易被 LLM 幻觉的字段。智能体在三个环节校验 URL 是否真实存在于文档原文中：

1. **源级校验**（接口分析后）：将 LLM 提取的接口 URL 与文档原文逐一比对，未命中的 URL 触发 LLM 纠错重试（最多 `url_doc_match_validation.max_retries` 次）。
2. **骨架级校验**（骨架生成后）：检查骨架中每个 URL 是否存在于文档原文，未命中的按 `url_check` 策略处理，并可调用 LLM 纠错。
3. **最终兜底校验**（写 YAML 前）：最后一次快速字符串存在性检查，仅标记不纠正。

### url_check 策略与失败处理

`url_check` 在 `validation.case_gen_validation.rules` 中配置策略（`skip`/`warn`/`fail`），当策略为 `warn` 时可附加 `failure_action` 子规则：

| failure_action | 行为 |
|----------------|------|
| `discard`（默认） | 无法纠正的用例写入 `failures.yaml`，标记后丢弃，不进入插件处理 |
| `keep` | 保留骨架，添加 URL 标记前缀，继续插件处理 |

无法纠正的 URL 会被标记（如 `<URL not exist>` / `[URL_MAY_INCORRECT]`）。执行器读到带此标记的用例会立即判失败，不会真正发起错误请求。

> **推荐配置**：URL 纠错建议全部设为 `warn`，重试全部失败时用 `keep` 保留。原因：LLM 难免出错，强模型也有低概率异常（如厂商 API 高峰期服务不稳定）。`warn + keep` 让流程不中断，同时把可疑用例明确标记出来交由人工复核，而非静默丢弃。

### 流程关联校验（flow_match）

`flow_match` 是计划解析阶段（第 9 步）的校验项，配置在 `validation.parse_plan_validation.rules` 中。

**作用**：计划解析完成后，系统将 LLM 输出的 Mermaid 流程图与需求分析阶段提取的业务场景进行关联匹配。若存在 Mermaid 图中描述但无法匹配到任何需求场景的"孤立流程"，说明 LLM 可能产生了幻觉（编造了需求中不存在的业务流程）。

**处理流程**：
1. 调用 `match_mermaids_to_scenarios()` 将每个 Mermaid 图与需求场景逐一匹配
2. 若存在失配，按 `strategy` 处理：
   - `fail`：抛出异常，终止流水线
   - `skip`：跳过校验，保留所有流程
   - `warn`：触发 LLM 纠错重试（最多 `max_retries` 次），重试耗尽后按 `failure_action` 处理

**failure_action**（仅 `strategy: warn` 时生效）：

| failure_action | 行为 |
|----------------|------|
| `discard`（默认） | 丢弃无法匹配的孤立流程，从计划中移除 |
| `keep` | 保留孤立流程，添加警告标记交由人工复核 |

> **推荐配置**：与 URL 纠错一致，建议 `warn + keep`。LLM 在生成 Mermaid 图时偶尔会产生需求中确实存在但匹配算法无法关联的合法流程，`keep` 确保不丢失有效测试场景。

---

## 插件错误处理

插件支持三种错误策略（`PluginDeclaration.error_strategy`）：

| 策略 | 行为 |
|------|------|
| `skip` | 跳过失败的插件，继续后续处理 |
| `warn` | 记录警告并继续 |
| `fail` | 终止流水线；可通过断点续写从失败阶段恢复 |

详见 [plugins-and-skills.md](./plugins-and-skills.md)。

---

## 数量纠错的重试上限

所有自动重试都受配置上限约束，避免无限循环：

- `case_gen_validation.max_retries`: 用例格式校验失败的重试次数（`validation` 段，原 `case_format_max_retries`）
- `url_doc_match_validation.max_retries`: URL 与文档原文匹配重试次数（`validation` 段，原 `url_doc_match_rules.max_retries`）
- `url_doc_match_validation.rules[url_check].strategy`: URL 纠错耗尽后策略（`validation` 段，`fail` | `warn` | `skip`）
- `consecutive_batch_failure_limit`：连续批次失败上限（`-1`=永不停止）

达到上限后按对应策略处理（终止 / 警告继续 / 标记）。
