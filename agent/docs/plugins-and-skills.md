# 插件与技能系统

[← 返回 agent/README](../README.md)

智能体通过**插件（Plugin）**在用例骨架生成后补充用例属性，通过**技能（Skill）**向各 Agent 注入领域知识与业务规则。两者均可插拔，无需修改框架代码。

---

## 插件系统

插件在用例骨架生成后运行，为骨架补充请求数据、断言等属性。所有插件通过 `env.yaml` 的 `plugins` 段配置：

```yaml
plugins:
  enabled: true          # 全局开关：false 时不加载任何插件
  modules:               # 按声明顺序依次执行
    - plugins.official.data_filling.DataFillingPlugin
    - plugins.official.processor_plugin.ProcessorPlugin
    - plugins.official.assertion_generation.AssertionGenerationPlugin
```

### 官方插件

| 插件 | 作用 | 适用范围 |
|------|------|----------|
| `data_filling` | 为用例骨架填充请求数据（`request_head`、`request_body`、`status_code`、`tag`） | 单接口 + 业务链路 |
| `processor_selection` | 为已填充用例分配前置/后置处理器（DB / Redis / MQ / RocketMQ） | 单接口 + 业务链路 |
| `assertion_generation` | 为已填充用例生成断言（`assert_dict`、`assert_rules`） | 单接口 + 业务链路 |

在 `plugins.modules` 中删减不需要的插件，或用自定义实现替换。

### 启用 / 禁用

- **全局禁用**：`plugins.enabled: false` → 跳过所有插件，仅生成骨架。
- **精细控制**：增删 `plugins.modules` 列表中的模块路径。

### 编写自定义插件

1. 继承 `CaseAttributeGenerator` 基类（`plugins/base.py`）
2. 声明 `PluginDeclaration`（插件名、作用属性、适用范围等）
3. 实现 `generate()` 方法（接收一批用例，返回补充属性后的用例列表）

```python
from plugins.base import CaseAttributeGenerator, PluginDeclaration

class CustomPlugin(CaseAttributeGenerator):
    @property
    def declaration(self):
        return PluginDeclaration(
            plugin_name="my-custom-plugin",
            attributes=["preprocessors"],
            applies_to_single=True,
            applies_to_biz=False,
            max_retries=1,
            error_strategy="skip",
        )

    def generate(self, cases, interfaces, api_summary, api_doc_text):
        for case in cases:
            case["preprocessors"] = [...]
        return cases
```

然后将插件路径加入 `env.yaml` 的 `plugins.modules` 即可。

### PluginDeclaration 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `plugin_name` | str | 插件名称 |
| `attributes` | List[str] | 要添加的属性名列表 |
| `applies_to_single` | bool | 是否作用于单接口用例 |
| `applies_to_biz` | bool | 是否作用于业务链路用例 |
| `max_retries` | int | 每批失败重试次数 |
| `error_strategy` | str | 彻底失败策略：`skip` / `warn` / `fail` |

`error_strategy` 为 `fail` 时，插件彻底失败会终止流水线，可通过断点续写从失败阶段恢复。

---

## 技能系统（Skill）

Skill 是插件的附属配置，以 YAML 文件形式存放，通过 `prompt_extension` 字段向 Agent 的系统提示词追加领域知识或业务规则，**不修改代码即可定制 Agent 行为**。设为关闭后插件仍正常运行，只是不加载 Skill 提供的额外提示词。

### 配置

```yaml
skills:
  enabled: true       # 全局开关：false 关闭所有 Skill 注入
  agents:             # 按目标 Agent 分配 Skill 文件（不含 .yaml 扩展名）
    # 插件 Agent
    data_filler:
      - foli_mall_data_filling
    assertion_generator:
      - foli_mall_assertion
    # 主流水线 Agent（按需取消注释）
    # case_generator:
    #   - boundary_test
```

### 可注入的 Agent

Skill 可注入到**所有** Agent（含主流水线 Agent 和插件内部 Agent）：

- **主流水线 Agent**：`requirement_analyzer`、`api_analyzer`、`plan_generator`、`plan_parser`、`case_generator`、`skeleton_generator`；Skill 存放于 `skills/builtin/`。
- **插件 Agent**：`data_filler`、`processor_selector`、`assertion_generator`；Skill 存放于 `plugins/official/skills/`。

### 内置 Skill

| Skill 文件 | 位置 | 作用 |
|-----------|------|------|
| `boundary_test.yaml` | `skills/builtin/` | 为 `case_generator` 注入边界值测试提示 |
| `foli_mall_data_filling.yaml` | `plugins/official/skills/` | Foli Mall 项目的数据填充规则 |
| `db_processors.yaml` | `plugins/official/skills/` | 可用的 DB 前后置处理器列表（用户可按模板扩展） |
| `redis_processors.yaml` | `plugins/official/skills/` | 可用的 Redis 缓存处理器列表 |
| `mq_processors.yaml` | `plugins/official/skills/` | 可用的 MQ 处理器列表（Kombu: RabbitMQ/Redis/SQS） |
| `rocketmq_processors.yaml` | `plugins/official/skills/` | 可用的 RocketMQ 处理器列表 |
| `kafka_processors.yaml` | `plugins/official/skills/` | 可用的 Kafka 处理器列表 |
| `pulsar_processors.yaml` | `plugins/official/skills/` | 可用的 Pulsar 处理器列表 |
| `utility_processors.yaml` | `plugins/official/skills/` | 工具类处理器参考（HMAC 签名、时间戳、调试等） |
| `foli_mall_assertion.yaml` | `plugins/official/skills/` | Foli Mall 项目的断言规则 |

### 启用 / 禁用

Skill 注入采用两层控制：

- **全局关闭**：`skills.enabled: false` → 所有 Skill 注入停止，插件正常运行。
- **精细控制**：编辑 `skills.agents`，注释/删除不需要的 Agent 或 Skill 条目。

### 多 Skill 配置示例

一个 Agent 可以加载多个 Skill 文件，系统会将它们合并注入到 LLM 系统提示词中。用户可以按需激活不同的处理器类别：

```yaml
skills:
  agents:
    processor_selector:
      - db_processors        # DB 处理器
      - redis_processors     # Redis 处理器
      # - mq_processors      # MQ 处理器（Kombu）
      # - rocketmq_processors # RocketMQ 处理器
      # - kafka_processors   # Kafka 处理器
      # - pulsar_processors  # Pulsar 处理器
```

### 使用建议

将待测项目的业务规则写入 Skill，例如：

- 接口约定的 HTTP 状态码（成功返回 200 vs 201）
- 认证方式（JWT Token、API Key、Session Cookie）
- 基础登录账号、测试数据字段格式

调试好 Skill 与插件后，可配合 `--auto` 自动模式进行无人值守的批量生成（见 [how-it-works.md](./how-it-works.md#自动模式auto-mode)）。
