# 处理器、断言引擎与报告

[← 返回 python/README](../README.md)

本文档覆盖执行器的内部机制：断言引擎、前置/后置处理器、登录态管理、HTML 报告，以及核心模块与执行流程。

---

## 断言引擎

### 简单断言（assert_dict）

- 对 HTTP 响应执行字段级等值断言。
- key 为 JSON 路径（支持点号 + 括号：`data.items[0].name`，也支持 `$.` 前缀）。
- `status_code` 字段特殊处理，针对 `response.status_code` 断言。
- 路径不存在时返回 `<not found>`。

### 高级断言（assert_rules）

每条规则是一个字符串表达式，格式为 `<左表达式> <运算符> [<右表达式>]`。

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `==` / `!=` | 等于 / 不等于 | `$.data.id == 1001` |
| `>` / `>=` / `<` / `<=` | 数值比较 | `$.data.total > 0` |
| `=~` | 正则匹配 | `$.data.time =~ ^\d{4}-\d{2}-\d{2}$` |
| `in` | 值在列表中 | `$.data.status in ["PAID", "PENDING"]` |
| `contains` | 集合包含元素 | `$.data.tags contains "vip"` |
| `not_contains` | 集合不包含元素 | `$.data.tags not_contains "blocked"` |
| `is_null` | 值为 null | `$.data.optional is_null` |
| `is_not_null` | 值不为 null | `$.data.order_id is_not_null` |
| `typeof` | 类型检查 | `$.data.count typeof int` |

支持函数：

| 函数 | 说明 | 示例 |
|------|------|------|
| `.length()` | 数组长度 | `$.data.list.length() == 3` |
| `SUM(path)` | 数组元素求和 | `SUM($.data.list[*].price)` |
| `SUM_PRODUCT(p1, p2)` | 两字段乘积求和 | `SUM_PRODUCT($.data.list[*].price, $.data.list[*].count)` |

路径中 `[*]` 表示遍历数组的每个元素，用于 `SUM` 和 `SUM_PRODUCT`。

---

## 前置处理器 / 后置处理器

在执行器发送 HTTP 请求前后，预留两个扩展点：

- **PreProcessor（前置处理器）** — 请求发送前执行，可修改请求头/体，适用于 HMAC 签名、参数加密、动态 Token 注入等。
- **PostProcessor（后置处理器）** — 断言执行后执行，可检查响应数据、执行外部清理（SQL、Redis）等。

处理器在用例中通过 `preprocessors` / `postprocessors` 字段声明，按列表顺序依次执行：

```yaml
preprocessors:
  - name: hmac-sign
    config:
      algorithm: sha256
      secret_env: SIGN_SECRET
```

Excel 中对应列值为 JSON 数组字符串：`[{"name": "hmac-sign", "config": {"algorithm": "sha256", "secret_env": "SIGN_SECRET"}}]`

### 敏感数据配置

密钥、数据库连接等敏感信息在 `env.yml` 的 `processor_configs` 段配置，执行时自动传递到处理器的 `global_config` 参数，无需在用例中明文书写：

```yaml
# env.yml
processor_configs:
  hmac-sign:
    secret_env: SIGN_SECRET
    algorithm: sha256
```

### 内置处理器

| 处理器 | 类型 | 说明 |
|--------|------|------|
| `hmac-sign` | Pre | HMAC-SHA256 请求签名，向请求头添加 `X-Signature` |
| `timestamp` | Pre | 注入 `X-Timestamp`（ISO 8601 UTC）和 `X-Request-Id`（UUIDv4） |
| `print-demo` | Pre | 调试用，INFO 级别打印请求摘要 |
| `path-param-restore` | Pre | 将 URL 路径参数替换时清除的字段恢复到请求体中 |
| `hmac-verify` | Post | HMAC-SHA256 响应签名校验，与 `hmac-sign` 配对 |
| `response-time` | Post | 记录响应状态码和内容长度，超过阈值时 WARNING |
| `print-demo-post` | Post | 调试用，INFO 级别打印响应摘要 |
| `return-order-db` | Pre + Post | 🌟 数据库处理器示例 — 前置 INSERT 订单，后置 print 退货记录（详见数据库处理器章节） |
| `mysql-demo` | Pre + Post | 🌟 MySQL 数据库示例 — 前置写入测试数据，后置读取并清理（详见数据库处理器章节） |
| `cache-handler` | Pre + Post | 🌟 Redis 缓存处理示例 — 前置写缓存，后置清缓存（详见 Redis 处理器章节） |
| `order-publish` | Pre + Post | 🌟 MQ 订单发布示例（Kombu）— 前置发布消息，后置消费验证（详见 MQ 处理器章节） |
| `rocketmq-order` | Pre + Post | 🌟 RocketMQ 订单消息示例 — 前置发送订单事件，后置消费校验（详见 RocketMQ 处理器章节） |
| `kafka-order-event` | Pre | 🌟 Kafka 订单事件示例 — 前置发送消息到 Kafka topic（详见 Kafka 处理器章节） |
| `pulsar-order-event` | Pre | 🌟 Pulsar 订单事件示例 — 前置发送消息到 Pulsar topic（详见 Pulsar 处理器章节） |

### URL 路径参数解析

URL 支持两种路径参数占位符：

- **`#{varName}`** — 从请求体取 `varName` 字段值替换，替换后默认从 body 移除该字段
- **`{varName}`** — 同上，适用于 RESTful 风格路径（如 `/api/stores/{id}`）

```yaml
# PUT /api/stores/{id}
request_body:
  id: 12345
  name: 测试门店
# → 请求 URL: PUT /api/stores/12345
# → 请求体: {"name": "测试门店"}（id 已移除并替换到 URL）
```

被移除的字段会记录在 `global_config["_cleared_path_params"]` 中，可通过 `path-param-restore` 前置处理器恢复到请求体，满足后端同时需要路径参数和 body 字段的场景：

```yaml
preprocessors:
  - name: path-param-restore
    config:
      fields: all            # "all"（恢复全部）或 ["id"] 指定字段名
```

### 自定义处理器

1. 继承 `PreProcessor` 或 `PostProcessor` 基类（`processors/base.py`）
2. 设置类属性 `name`（对应用例中引用的名称）
3. 实现 `process()` 方法
4. 将 `.py` 文件放入 `processors/` 目录

```python
from processors.base import PreProcessor

class MyPreProcessor(PreProcessor):
    name = "my-processor"

    def process(self, headers, body, case_config, global_config):
        # 修改 headers / body
        return headers, body
```

### 数据库处理器（BaseDBPlugin）

对于需要数据库操作的前置/后置场景（如"请求前造测试数据、请求后清理"），可使用 `BaseDBPlugin` 基类（`processors/db.py`）。它基于 **SQLAlchemy** 提供：

- **多数据库支持**：MySQL、PostgreSQL、SQLite、Oracle、MSSQL 等，通过 `db_url` 连接字符串切换
- **连接池管理**：SQLAlchemy 内置 `QueuePool`，线程安全、懒加载、按 `db_url` 缓存
- **自动注册**：`__init_subclass__` 自动创建 PreProcessor / PostProcessor 包装类
- **共享基类**：`BaseExternalPlugin`（`processors/base.py`）统一提供 `can_process()` / `before_request()` / `after_response()` 三个扩展点的默认实现，DB/Redis/MQ/Kafka/Pulsar/RocketMQ 六类资源插件均继承自此基类

使用方式：

1. 继承 `BaseDBPlugin`，设置 `name` 类属性
2. 实现 `before_request()`（前置）和/或 `after_response()`（后置）
3. 将 `.py` 文件放入 `processors/builtin/db/` 目录
4. 在 `env-local.yml` 的 `processor_configs` 中配置 `db_url`

```python
from processors.db import BaseDBPlugin
from sqlalchemy import text

class MyDBPlugin(BaseDBPlugin):
    name = "my-db-processor"

    def before_request(self, headers, body, case_config, global_config):
        with self._get_connection(global_config) as conn:
            conn.execute(text("INSERT INTO ..."))
            conn.commit()
            body["new_id"] = ...
        return headers, body

    def after_response(self, req_h, req_b, resp_h, resp_b, cc, gc):
        with self._get_connection(gc) as conn:
            rows = conn.execute(text("SELECT ...")).fetchall()
            print("Result:", rows)
```

用例 YAML 中引用（与普通处理器相同）：

```yaml
preprocessors:
  - name: my-db-processor
    config: {}
postprocessors:
  - name: my-db-processor
    config: {}
```

**内置示例**：`return-order-db`（`processors/builtin/db/return_order.py`）— 退货单场景，前置 INSERT 订单数据，后置 print 退货记录。

> 该示例对应 foli-mall 的 `POST /api/returns` 退货接口：前置处理器默认创建 `status=4`（已完成）的测试订单，并把 `orderId` 注入请求体（与 `ReturnCreateRequest` 的驼峰字段一致）；后置处理器查询并打印退货记录。可用 `order_status` 配置项覆盖订单状态。

> **配置说明**：数据库连接通过 `env-local.yml` 的 `processor_configs.<name>.db_url` 配置（SQLAlchemy connection URL 格式）。不需要在用例 YAML 中暴露敏感信息。
>
> **依赖安装**：`pip install sqlalchemy pymysql`（MySQL）；其他数据库需安装对应驱动（如 `psycopg2`、`cx_Oracle`）。
>
> **H2 支持**：安装 `pip install JPype1 JayDeBeApi`，`db_url` 配置为 `h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false`（对应 foli-mall 的 H2 内存库）。H2 SQLAlchemy 方言内置在 `processors/h2_dialect.py`，通过 JayDeBeApi 自动加载 H2 JDBC jar（无需手工设置 CLASSPATH）。jar 不随仓库分发，请先用初始化脚本下载：
>
> ```bash
> python tools/h2/init_h2.py                # 下载到默认目录 ~/.flow-forge/h2/
> python tools/h2/init_h2.py --dir D:/h2    # 或下载到自定义目录
> python tools/h2/init_h2.py --check        # 仅检查是否已就绪
> ```
>
> 方言按以下顺序自动探测 jar：`H2_JAR_PATH`（完整路径）→ `H2_JAR_DIR`（目录）→ 默认目录 `~/.flow-forge/h2/` → 旧位置 `tools/h2/`（向后兼容）。使用自定义目录时请设置 `H2_JAR_DIR` 环境变量。
>
> foli-mall 后端启动时会自动开启 H2 TCP Server（默认端口 9092，配置项 `app.h2.tcp.enabled` / `app.h2.tcp.port`），无需手工启动。H2 为内存数据库，重启后数据清空，请按以下顺序运行：
>
> 1. 启动 foli-mall 后端（如 `./mvnw spring-boot:run`）；
> 2. 在已安装 `JPype1`/`JayDeBeApi` 的 Python 环境中运行 flow-forge 用例。

**内置示例（MySQL）**：`mysql-demo`（`processors/builtin/db/mysql_demo.py`）— 前置处理器自动创建示例表 `ff_plugin_demo`（如不存在）并写入一行测试数据，再把 `mysql_demo_key` 注入请求体；后置处理器 SELECT 校验数据可读并 print 展示，随后 DELETE 并再次校验无残留。该插件用于验证 flow-forge 数据库处理器可连接 MySQL，同时作为自定义 DB 插件的样板。

> **配置说明**：通过 `processor_configs.<name>.db_url` 配置 MySQL 连接（SQLAlchemy URL 格式），例如 `mysql+pymysql://root:password@localhost:3306/flow_forge_demo?charset=utf8mb4`；示例表会自动创建，无需手工建表。

### Redis 处理器（BaseRedisPlugin）

对于需要 Redis 缓存操作的前置/后置场景（如"请求前写缓存、请求后清理"），可使用 `BaseRedisPlugin` 基类（`processors/redis.py`）。它基于 **redis-py** 提供：

- **连接池管理**：redis-py 内置 `ConnectionPool`，线程安全、懒加载、按 `redis_url` 缓存客户端
- **自动注册**：`__init_subclass__` 自动创建 PreProcessor / PostProcessor 包装类

使用方式与 `BaseDBPlugin` 相同：继承 → 设置 `name` → 实现 `before_request()` / `after_response()`。

**内置示例**：`cache-handler`（`processors/builtin/redis/cache_handler.py`）— 前置 SET 缓存数据，后置 DEL 清理。

> **配置说明**：Redis 连接通过 `processor_configs.<name>.redis_url` 配置。
> **依赖安装**：`pip install redis`
> **协议兼容**：客户端会自动探测协议兼容性——新版 redis-py 默认 RESP3，若服务器不支持（如 Redis 5.x 无 `HELLO` 命令）则自动降级为 RESP2，兼容 Redis 5.x 与 6+/7。

### MQ 处理器 — Kombu 多 MQ 抽象（BaseMQPlugin）

对于需要消息队列操作的前置/后置场景，可使用 `BaseMQPlugin` 基类（`processors/mq.py`）。它基于 **Kombu**（Celery 的传输层）提供多 MQ 抽象——类似 SQLAlchemy 对数据库的作用：

- **多 MQ 支持**：一个 `mq_url` 连接字符串切换 RabbitMQ / Redis / Amazon SQS / MongoDB 等
- **连接管理**：Kombu `Connection` 自带连接池，线程安全、懒加载、按 `mq_url` 缓存
- **自动注册**：`__init_subclass__` 自动创建 PreProcessor / PostProcessor 包装类
- **便捷方法**：`_publish()` 发布消息、`_get_message()` 消费消息

支持的协议：

| 协议 | `mq_url` 示例 | MQ 系统 |
|------|-------------|--------|
| `amqp://` | `amqp://guest:guest@localhost:5672//` | RabbitMQ |
| `redis://` | `redis://localhost:6379/0` | Redis (as broker) |
| `sqs://` | `sqs://AWS_KEY:AWS_SECRET@` | Amazon SQS |
| `memory://` | `memory://` | 测试用（无需外部服务） |

**内置示例**：`order-publish`（`processors/builtin/mq/order_publish.py`）— 前置 publish 订单事件，后置 consume 验证。

> **依赖安装**：`pip install kombu`

### RocketMQ 处理器（BaseRocketMQPlugin）

Apache RocketMQ 在国内是主流 MQ，因其协议特殊（Kombu 不支持），单独提供 `BaseRocketMQPlugin` 基类（`processors/rocketmq.py`）。内置基于 remoting 协议的纯 Python 客户端（`processors/rocketmq_client.py`，仅标准库），Windows/Linux/macOS 均可收发消息，无需 C++ 编译环境：

- **连接管理**：`_RocketMQManager` 按 `namesrv_addr` 缓存客户端，线程安全
- **便捷方法**：`_send_message()` 发送消息（返回 queueId/queueOffset 等元数据）、`_receive_message()` 从指定偏移消费消息（使用独立的 `<group>-verify` 消费组）
- **自动注册**：与 DB/Redis/MQ 相同模式

**内置示例**：`rocketmq-order`（`processors/builtin/rocketmq/order_message.py`）— 前置发送 `order_created` 订单事件，后置从同一偏移消费并校验消息内容；校验失败（超时或不匹配）会使用例失败。

> **配置说明**：连接通过 `processor_configs.<name>.namesrv_addr`、`group_id`、`topic` 配置。
> `receive_timeout`（默认 10 秒）控制后置消费校验超时。
> **依赖说明**：无需安装额外依赖；官方 `rocketmq-client-python` 不支持 Windows，故内置纯 Python 客户端。

### Kafka 处理器（BaseKafkaPlugin）

对于需要 Kafka 消息发送的前置/后置场景，可使用 `BaseKafkaPlugin` 基类（`processors/kafka.py`）。它基于 **confluent-kafka**（Confluent 官方 Python 客户端）提供：

- **连接管理**：`_KafkaProducerManager` 按 `(bootstrap_servers, client_id)` 缓存 Producer，线程安全
- **便捷方法**：`_send_message()` 同步发送消息
- **自动注册**：与 DB/Redis/MQ/RocketMQ 相同模式

**内置示例**：`kafka-order-event`（`processors/builtin/kafka/order_event.py`）— 前置发送订单事件到 Kafka topic。

> **配置说明**：连接通过 `processor_configs.<name>.bootstrap_servers`、`topic` 配置。
> **依赖安装**：`pip install confluent-kafka`

### Pulsar 处理器（BasePulsarPlugin）

对于需要 Pulsar 消息发送的前置/后置场景，可使用 `BasePulsarPlugin` 基类（`processors/pulsar.py`）。它基于 **pulsar-client**（Apache Pulsar 官方 Python 客户端）提供：

- **连接管理**：`_PulsarClientManager` 按 `service_url` 缓存 Client，线程安全
- **便捷方法**：`_send_message()` 同步发送消息
- **自动注册**：与 DB/Redis/MQ/RocketMQ/Kafka 相同模式

**内置示例**：`pulsar-order-event`（`processors/builtin/pulsar/order_event.py`）— 前置发送订单事件到 Pulsar topic。

> **配置说明**：连接通过 `processor_configs.<name>.service_url`、`topic` 配置。
> **依赖安装**：`pip install pulsar-client`

### 执行流程

```
请求前: Token 解析 → PreProcessors（按顺序） → 发送请求
请求后: 断言执行 → PostProcessors（按顺序） → 报告生成
```

处理器抛出的 `ProcessorError` 会终止用例执行（PreProcessor 失败不发送请求），错误信息同步显示在报告中；PostProcessor 失败记录错误并继续报告。

---

## 登录态管理器

线程安全的 Token 管理（`auth/login_manager.py`）：

```
检测 #{userParamName} → 查缓存 → 命中返回 Token
                              → 未命中 → 查失败黑名单 → 在黑名单则跳过
                                                     → 不在黑名单 → 获取用户锁
                                                       → POST 登录接口
                                                       → 成功：缓存 Token，返回
                                                       → 失败：加黑名单，返回错误
```

支持嵌入式占位符（`"#{normalUser}"` 和 `"Bearer #{normalUser}"` 均可），使用通用 `#{}` 解析器逐占位符替换。关键设计：

- **细粒度锁**：按 `appName:userParamName` 粒度锁定，不同用户可并发登录
- **失败黑名单**：MD5 哈希记录登录失败用户，避免重复无效请求
- **Token 缓存**：同一用户只需登录一次，后续复用
- **用户上下文追踪**（v2.5+）：线程局部存储记录当前解析的 `userParamName` 和 `appConfig`，提供三个工具方法供插件使用：
  - `LoginManager.get_current_user()` — 无参，获取当前登录用户的完整配置（含 `user_id` / `role` 等冗余字段）
  - `LoginManager.get_user(user_param_name)` — 获取当前 App 下指定用户的配置
  - `LoginManager.get_app_user(app_name, user_param_name)` — 完整显式查找，不依赖线程上下文

---

## HTML 报告

生成自包含的 HTML 报告（`reporter/html_writer.py`，无需外部 CSS/JS）：

- **摘要区**：环境名、测试时间、总用例数
- **单接口用例区**：可折叠列表，失败优先排序，每个用例卡片含请求/响应详情（JSON 格式化）、断言结果表（字段/预期/实际/通过失败）、处理器结果
- **业务链路用例区**：每流一张卡片，展示执行链路（成功 `→`、失败 `×`）和每步骤详情
- 通过/失败分别用绿色/红色标识
- 报告输出到 `python/report/` 目录，文件名格式 `{Excel文件名}_{时间戳}.html`

---

## 核心模块

```text
python/
├── main.py                 # CLI 入口，流程编排（执行器）
├── converter_main.py       # CLI 入口，格式转换
├── config/config_manager.py # 配置加载、合并、CLI 覆盖（单例）
├── excel_reader/           # 多 Sheet Excel 解析、校验
├── yaml_reader/            # YAML 用例文件/目录解析
├── resolvers/              # JSON 路径解析 + #{}/{} 占位符解析
├── executor/               # BaseExecutor（线程池）+ Single/Biz 执行器 + 工厂
├── auth/                   # 线程安全登录态管理器
├── assertion/              # 简单断言引擎 + 高级断言规则引擎
├── processors/             # 前置/后置处理器（基类 + 加载器 + 内置）
├── converter/              # Excel ↔ YAML 转换 + pytest 生成
├── reporter/               # 自包含 HTML 报告生成器
└── i18n/                   # 国际化（zh_CN / en_US）
```

- **配置管理器**：加载 `env.yml` → 合并 `env-{envName}.yml`（区分顶层配置与应用配置）→ 应用 CLI 覆盖 → 提供 `get()` / `get_all()` / `get_app()`。
- **Excel 解析器**：按 `apiMode` 读取单接口/业务链路 Sheet，对业务链路执行 `Inherit` 校验和 `StepID` 去重，解析异常返回 `parse_error` 不阻塞其他用例。
- **YAML 解析器**：`parse_directory()`（递归扫描）与 `parse_files()`（逗号分隔列表）；通过 `case_type` 区分类型，缺失时按结构自动推断（含 `steps`→业务链路，含 `test_id`→单接口）；按 `apiMode` 过滤，返回与 Excel 解析器一致的数据结构。
- **执行器**：`BaseExecutor` 提供 `ThreadPoolExecutor` 线程池（并发数由 `maxThread` 控制）和线程安全结果收集；`SingleCaseExecutor` 并发执行单接口用例；`BizFlowExecutor` 每个业务流一线程、流内步骤串行、任一步失败即中止后续，用 `threading.local()` 存每线程步骤响应，请求头 `#{}` 采用「Inherit 优先、LoginManager 回退」策略。

---

## 执行流程图

### 单接口测试流程

```mermaid
sequenceDiagram
    participant CLI
    participant Config
    participant Excel
    participant Executor
    participant LoginMgr
    participant API
    participant Assert

    CLI->>Config: 加载配置
    Config->>Excel: 解析用例文件
    Excel->>Executor: 单接口用例列表
    loop 每个用例（线程池并发）
        Executor->>LoginMgr: 解析 Token (#{user})
        LoginMgr-->>Executor: 带 Token 的请求头
        Executor->>API: 发送 HTTP 请求
        API-->>Executor: 响应
        Executor->>Assert: 执行断言
        Assert-->>Executor: 断言结果
    end
    Executor->>CLI: 汇总结果 → HTML 报告
```

### 业务链路测试流程

```mermaid
sequenceDiagram
    participant Thread
    participant BizFlow
    participant LoginMgr
    participant API

    Thread->>BizFlow: 执行业务流（每流一线程）
    loop 步骤串行执行
        BizFlow->>BizFlow: 解析 Inherit 变量 (#{key})
        BizFlow->>LoginMgr: 解析 Token
        BizFlow->>API: 发送 HTTP 请求
        API-->>BizFlow: 响应
        BizFlow->>BizFlow: 存储响应到 ThreadLocal
        BizFlow->>BizFlow: 执行断言
        alt 断言失败
            BizFlow->>BizFlow: 中止后续步骤，记录失败步骤
        end
    end
```

---

## 输入校验与错误处理

- **YAML 必填字段校验**：单接口用例需 `test_id`/`method`/`url`；业务链路用例需 `sheet_name` 和非空 `steps`。缺失时警告并跳过，不计入总数。
- **空业务链路拒绝**：`steps` 为空列表返回失败结果，而非「通过」。
- **URL 空值安全**：`url` 为 `None` 时正常报错，不崩溃。
- **URL 标记校验**：URL 含 `<URL not exist>` 标记（Agent 生成阶段注入）时立即判失败，不发起请求。
- **Excel 列校验**：单接口 sheet 需 `TestID` 列，业务链路 sheet 需 `StepID` 列，缺失抛 `ValueError` 并以退出码 2 终止。

退出码见 [配置与命令行参考](./configuration.md#退出码)。
