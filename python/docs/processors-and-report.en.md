# Processors, Assertion Engine & Reports

[← Back to python/README](../README.en.md)

This document covers the executor's internal mechanics: the assertion engine, pre-/post-processors, login/session management, HTML reports, plus the core modules and the execution flow.

---

## Assertion Engine

### Simple Assertions (assert_dict)

- Performs field-level equality assertions on the HTTP response.
- Keys are JSON paths (supporting dot + bracket notation: `data.items[0].name`, and also the `$.` prefix).
- The `status_code` field is special-cased and asserted against `response.status_code`.
- A missing path renders as `<not found>`.

### Advanced Assertions (assert_rules)

Each rule is a string expression in the format `<left expression> <operator> [<right expression>]`.

| Operator | Description | Example |
|--------|------|------|
| `==` / `!=` | Equal / Not equal | `$.data.id == 1001` |
| `>` / `>=` / `<` / `<=` | Numeric comparison | `$.data.total > 0` |
| `=~` | Regex match | `$.data.time =~ ^\d{4}-\d{2}-\d{2}$` |
| `in` | Value is in list | `$.data.status in ["PAID", "PENDING"]` |
| `contains` | Collection contains element | `$.data.tags contains "vip"` |
| `not_contains` | Collection does not contain element | `$.data.tags not_contains "blocked"` |
| `is_null` | Value is null | `$.data.optional is_null` |
| `is_not_null` | Value is not null | `$.data.order_id is_not_null` |
| `typeof` | Type check | `$.data.count typeof int` |

Supported functions:

| Function | Description | Example |
|------|------|------|
| `.length()` | Array length | `$.data.list.length() == 3` |
| `SUM(path)` | Sum of array elements | `SUM($.data.list[*].price)` |
| `SUM_PRODUCT(p1, p2)` | Sum of the products of two fields | `SUM_PRODUCT($.data.list[*].price, $.data.list[*].count)` |

The `[*]` wildcard in a path iterates over each element of an array, used with `SUM` and `SUM_PRODUCT`.

---

## Pre-processors / Post-processors

Two extension points are reserved before and after the executor sends an HTTP request:

- **PreProcessor (pre-processor)** — Runs before the request is sent; can modify the request headers/body. Suitable for HMAC signing, parameter encryption, dynamic token injection, etc.
- **PostProcessor (post-processor)** — Runs after assertions; can inspect response data, perform external cleanup (SQL, Redis), etc.

Processors are declared in cases via the `preprocessors` / `postprocessors` fields and run sequentially in list order:

```yaml
preprocessors:
  - name: hmac-sign
    config:
      algorithm: sha256
      secret_env: SIGN_SECRET
```

The corresponding Excel column value is a JSON array string: `[{"name": "hmac-sign", "config": {"algorithm": "sha256", "secret_env": "SIGN_SECRET"}}]`

### Sensitive Data Configuration

Sensitive information such as secrets and database connections is configured in the `processor_configs` section of `env.yml` and passed automatically to the processor's `global_config` parameter at runtime, so it never has to be written in plaintext in cases:

```yaml
# env.yml
processor_configs:
  hmac-sign:
    secret_env: SIGN_SECRET
    algorithm: sha256
```

### Built-in Processors

| Processor | Type | Description |
|--------|------|------|
| `hmac-sign` | Pre | HMAC-SHA256 request signing; adds the `X-Signature` header |
| `timestamp` | Pre | Injects `X-Timestamp` (ISO 8601 UTC) and `X-Request-Id` (UUIDv4) |
| `print-demo` | Pre | Debug helper; logs the request summary at INFO level |
| `path-param-restore` | Pre | Restores fields cleared during URL path parameter substitution back into the request body |
| `hmac-verify` | Post | HMAC-SHA256 response signature verification; pairs with `hmac-sign` |
| `response-time` | Post | Logs the response status code and content length; warns when a threshold is exceeded |
| `print-demo-post` | Post | Debug helper; logs the response summary at INFO level |
| `return-order-db` | Pre + Post | 🌟 DB processor example — pre-inserts an order, post-prints the return record (see Database Processors section) |
| `cache-handler` | Pre + Post | 🌟 Redis cache handler example — pre-set cache, post-delete (see Redis Processors section) |
| `order-publish` | Pre + Post | 🌟 MQ order publish example (Kombu) — pre-publish message, post-consume verify (see MQ Processors section) |
| `rocketmq-order` | Pre | 🌟 RocketMQ order message example — pre-send message to RocketMQ topic (see RocketMQ Processors section) |
| `kafka-order-event` | Pre | 🌟 Kafka order event example — pre-send message to Kafka topic (see Kafka Processors section) |
| `pulsar-order-event` | Pre | 🌟 Pulsar order event example — pre-send message to Pulsar topic (see Pulsar Processors section) |

### URL Path Parameter Resolution

URLs support two path parameter placeholder formats:

- **`#{varName}`** — Takes the value of the `varName` field from the request body and substitutes it; by default the field is then removed from the body
- **`{varName}`** — Same as above, suitable for RESTful-style paths (e.g., `/api/stores/{id}`)

```yaml
# PUT /api/stores/{id}
request_body:
  id: 12345
  name: Test Store
# → Request URL: PUT /api/stores/12345
# → Request body: {"name": "Test Store"} (id was removed and substituted into the URL)
```

Removed fields are recorded in `global_config["_cleared_path_params"]` and can be restored to the request body by the `path-param-restore` pre-processor, for backends that require both a path parameter and the corresponding body field:

```yaml
preprocessors:
  - name: path-param-restore
    config:
      fields: all            # "all" (restore everything) or ["id"] for specific field names
```

### Custom Processors

1. Inherit from the `PreProcessor` or `PostProcessor` base class (`processors/base.py`)
2. Set the class attribute `name` (matching the name referenced in cases)
3. Implement the `process()` method
4. Place the `.py` file in the `processors/` directory

```python
from processors.base import PreProcessor

class MyPreProcessor(PreProcessor):
    name = "my-processor"

    def process(self, headers, body, case_config, global_config):
        # Modify headers / body
        return headers, body
```

### Database Processors (BaseDBPlugin)

For scenarios that need database operations before/after requests (e.g., "create test data before request, clean up after"), use the `BaseDBPlugin` base class (`processors/db.py`). Built on **SQLAlchemy**, it provides:

- **Multi-database support**: MySQL, PostgreSQL, SQLite, Oracle, MSSQL, etc., switched via `db_url` connection string
- **Connection pooling**: SQLAlchemy's built-in `QueuePool` — thread-safe, lazy-loaded, cached by `db_url`
- **Auto-registration**: `__init_subclass__` auto-creates PreProcessor / PostProcessor wrapper classes
- **Shared base**: `BaseExternalPlugin` (`processors/base.py`) provides default implementations for the three extension points — `can_process()` / `before_request()` / `after_response()` — from which all six resource plugin categories (DB/Redis/MQ/Kafka/Pulsar/RocketMQ) inherit

Usage:

1. Subclass `BaseDBPlugin`, set `name` class attribute
2. Implement `before_request()` (pre) and/or `after_response()` (post)
3. Place the `.py` file in `processors/builtin/db/`
4. Configure `db_url` in `env-local.yml` under `processor_configs`

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

Reference in test case YAML (same as regular processors):

```yaml
preprocessors:
  - name: my-db-processor
    config: {}
postprocessors:
  - name: my-db-processor
    config: {}
```

**Built-in example**: `return-order-db` (`processors/builtin/db/return_order.py`) — return/refund scenario: pre-inserts order data, post-prints return record.

> **Configuration**: Database connection is configured via `processor_configs.<name>.db_url` in `env-local.yml` (SQLAlchemy connection URL format). No sensitive info in test case YAML.
>
> **Dependencies**: `pip install sqlalchemy pymysql` (MySQL); install the corresponding driver for other databases (e.g., `psycopg2`, `cx_Oracle`).

### Redis Processors (BaseRedisPlugin)

For scenarios requiring Redis cache operations before/after requests (e.g., "set cache before request, clean up after"), use the `BaseRedisPlugin` base class (`processors/redis.py`). Built on **redis-py**, it provides:

- **Connection pooling**: redis-py's built-in `ConnectionPool` — thread-safe, lazy-loaded, cached by `redis_url`
- **Auto-registration**: `__init_subclass__` auto-creates PreProcessor / PostProcessor wrapper classes

Usage follows the same pattern as `BaseDBPlugin`: subclass → set `name` → implement `before_request()` / `after_response()`.

**Built-in example**: `cache-handler` (`processors/builtin/redis/cache_handler.py`) — pre SET cache data, post DEL cleanup.

> **Configuration**: Redis connection via `processor_configs.<name>.redis_url`.
> **Dependencies**: `pip install redis`

### MQ Processors — Kombu Multi-MQ Abstraction (BaseMQPlugin)

For scenarios requiring message queue operations, use the `BaseMQPlugin` base class (`processors/mq.py`). Built on **Kombu** (Celery's transport layer), it provides multi-MQ abstraction — like SQLAlchemy for databases:

- **Multi-MQ support**: One `mq_url` connection string for RabbitMQ / Redis / Amazon SQS / MongoDB
- **Connection management**: Kombu `Connection` with built-in pooling — thread-safe, lazy-loaded, cached by `mq_url`
- **Auto-registration**: `__init_subclass__` auto-creates PreProcessor / PostProcessor wrapper classes
- **Convenience methods**: `_publish()` for message publishing, `_get_message()` for message consuming

Supported protocols:

| Protocol | `mq_url` example | MQ System |
|------|-------------|--------|
| `amqp://` | `amqp://guest:guest@localhost:5672//` | RabbitMQ |
| `redis://` | `redis://localhost:6379/0` | Redis (as broker) |
| `sqs://` | `sqs://AWS_KEY:AWS_SECRET@` | Amazon SQS |
| `memory://` | `memory://` | Testing (no external service needed) |

**Built-in example**: `order-publish` (`processors/builtin/mq/order_publish.py`) — pre publish order event, post consume verify.

> **Dependencies**: `pip install kombu`

### RocketMQ Processors (BaseRocketMQPlugin)

Apache RocketMQ is widely used. Its protocol differs from AMQP/Redis (not supported by Kombu), so a separate `BaseRocketMQPlugin` is provided (`processors/rocketmq.py`). Uses the `rocketmq-client-python` official client:

- **Connection management**: `_RocketMQManager` caches Producer by `(namesrv_addr, group_id)`, thread-safe
- **Convenience method**: `_send_message()` for synchronous message sending
- **Auto-registration**: Same pattern as DB/Redis/MQ

**Built-in example**: `rocketmq-order` (`processors/builtin/rocketmq/order_message.py`) — pre send order event to RocketMQ topic.

> **Configuration**: Connection via `processor_configs.<name>.namesrv_addr`, `group_id`, `topic`.
> **Dependencies**: `pip install rocketmq-client-python` (requires C++ build environment)

### Kafka Processors (BaseKafkaPlugin)

For scenarios requiring Kafka message sending before/after requests, use the `BaseKafkaPlugin` base class (`processors/kafka.py`). Built on **confluent-kafka** (Confluent's official Python client), it provides:

- **Connection management**: `_KafkaProducerManager` caches Producer by `(bootstrap_servers, client_id)`, thread-safe
- **Convenience method**: `_send_message()` for synchronous message sending
- **Auto-registration**: Same pattern as DB/Redis/MQ/RocketMQ

**Built-in example**: `kafka-order-event` (`processors/builtin/kafka/order_event.py`) — pre send order event to Kafka topic.

> **Configuration**: Connection via `processor_configs.<name>.bootstrap_servers`, `topic`.
> **Dependencies**: `pip install confluent-kafka`

### Pulsar Processors (BasePulsarPlugin)

For scenarios requiring Pulsar message sending before/after requests, use the `BasePulsarPlugin` base class (`processors/pulsar.py`). Built on **pulsar-client** (Apache Pulsar's official Python client), it provides:

- **Connection management**: `_PulsarClientManager` caches Client by `service_url`, thread-safe
- **Convenience method**: `_send_message()` for synchronous message sending
- **Auto-registration**: Same pattern as DB/Redis/MQ/RocketMQ/Kafka

**Built-in example**: `pulsar-order-event` (`processors/builtin/pulsar/order_event.py`) — pre send order event to Pulsar topic.

> **Configuration**: Connection via `processor_configs.<name>.service_url`, `topic`.
> **Dependencies**: `pip install pulsar-client`

### Execution Flow

```
Before request: token resolution → PreProcessors (in order) → send request
After request:  assertion execution → PostProcessors (in order) → report generation
```

A `ProcessorError` raised by a processor terminates case execution (a PreProcessor failure means no request is sent), and the error message is shown in the report; a PostProcessor failure records the error and continues to reporting.

---

## Login/Session Manager

Thread-safe token management (`auth/login_manager.py`):

```
Detect #{userParamName} → check cache → hit: return token
                                      → miss → check failure blacklist → blacklisted: skip
                                                                       → not blacklisted → acquire user lock
                                                                         → POST login endpoint
                                                                         → success: cache token, return
                                                                         → failure: add to blacklist, return error
```

Embedded placeholders are supported (both `"#{normalUser}"` and `"Bearer #{normalUser}"` work), using the generic `#{}` resolver for per-placeholder substitution. Key design choices:

- **Fine-grained locks**: locking at `appName:userParamName` granularity; different users can log in concurrently
- **Failure blacklist**: records failed-login users by MD5 hash to avoid repeated invalid requests
- **Token cache**: each user logs in only once; subsequent calls reuse the cached token
- **User context tracking** (v2.5+): thread-local storage records the currently resolved `userParamName` and `appConfig`, exposing three utility methods for plugins:
  - `LoginManager.get_current_user()` — no args; returns the full config of the currently logged-in user (including extra fields like `user_id` / `role`)
  - `LoginManager.get_user(user_param_name)` — returns the config for a named user in the current app
  - `LoginManager.get_app_user(app_name, user_param_name)` — full explicit lookup, independent of thread context

---

## HTML Reports

Generates self-contained HTML reports (`reporter/html_writer.py`, no external CSS/JS required):

- **Summary section**: environment name, test time, total case count
- **Single-API cases section**: collapsible list, sorted with failures first; each case card includes request/response details (JSON-formatted), an assertion results table (field/expected/actual/pass-fail), and processor results
- **Business-flow cases section**: one card per flow, showing the execution chain (success `→`, failure `×`) and per-step details
- Pass/fail indicated in green/red respectively
- Reports are written to the `python/report/` directory; filename format `{ExcelFileName}_{timestamp}.html`

---

## Core Modules

```text
python/
├── main.py                 # CLI entry point, workflow orchestration (executor)
├── converter_main.py       # CLI entry point, format conversion
├── config/config_manager.py # config loading, merging, CLI override (singleton)
├── excel_reader/           # multi-sheet Excel parsing and validation
├── yaml_reader/            # YAML case file/directory parsing
├── resolvers/              # JSON path resolution + #{}/{} placeholder resolution
├── executor/               # BaseExecutor (thread pool) + Single/Biz executors + factory
├── auth/                   # thread-safe login/session manager
├── assertion/              # simple assertion engine + advanced assertion rules engine
├── processors/             # pre-/post-processors (base classes + loader + built-ins)
├── converter/              # Excel ↔ YAML conversion + pytest generation
├── reporter/               # self-contained HTML report generator
└── i18n/                   # internationalization (zh_CN / en_US)
```

- **Config manager**: loads `env.yml` → merges `env-{envName}.yml` (separating top-level config from application config) → applies CLI overrides → provides `get()` / `get_all()` / `get_app()`.
- **Excel parser**: reads single-API/business-flow sheets per `apiMode`, performs `Inherit` validation and `StepID` deduplication for business flows, and returns `parse_error` on parsing exceptions without blocking other cases.
- **YAML parser**: `parse_directory()` (recursive scan) and `parse_files()` (comma-separated list); distinguishes types by `case_type`, auto-inferring from structure when missing (has `steps` → business flow, has `test_id` → single-API); filters by `apiMode` and returns a data structure identical to the Excel parser's.
- **Executors**: `BaseExecutor` provides a `ThreadPoolExecutor` thread pool (concurrency controlled by `maxThread`) and thread-safe result collection; `SingleCaseExecutor` runs single-API cases concurrently; `BizFlowExecutor` runs one thread per business flow with steps executed sequentially within a flow, aborting subsequent steps as soon as any step fails, uses `threading.local()` to store per-thread step responses, and applies an "Inherit-first, LoginManager fallback" strategy for `#{}` in request headers.

---

## Execution Flow Diagrams

### Single-API Test Flow

```mermaid
sequenceDiagram
    participant CLI
    participant Config
    participant Excel
    participant Executor
    participant LoginMgr
    participant API
    participant Assert

    CLI->>Config: Load config
    Config->>Excel: Parse case file
    Excel->>Executor: Single-API case list
    loop Each case (thread pool concurrent)
        Executor->>LoginMgr: Resolve token (#{user})
        LoginMgr-->>Executor: Headers with token
        Executor->>API: Send HTTP request
        API-->>Executor: Response
        Executor->>Assert: Run assertions
        Assert-->>Executor: Assertion results
    end
    Executor->>CLI: Summarize results → HTML report
```

### Business-Flow Test Flow

```mermaid
sequenceDiagram
    participant Thread
    participant BizFlow
    participant LoginMgr
    participant API

    Thread->>BizFlow: Execute business flow (one flow per thread)
    loop Steps execute sequentially
        BizFlow->>BizFlow: Resolve Inherit variables (#{key})
        BizFlow->>LoginMgr: Resolve token
        BizFlow->>API: Send HTTP request
        API-->>BizFlow: Response
        BizFlow->>BizFlow: Store response in ThreadLocal
        BizFlow->>BizFlow: Run assertions
        alt Assertion failed
            BizFlow->>BizFlow: Abort subsequent steps, record failed step
        end
    end
```

---

## Input Validation & Error Handling

- **YAML required field validation**: single-API cases require `test_id`/`method`/`url`; business-flow cases require `sheet_name` and a non-empty `steps`. Missing fields trigger a warning and the case is skipped, not counted in the total.
- **Empty business-flow rejection**: an empty `steps` list returns a failure result rather than "passed".
- **URL null safety**: a `url` of `None` reports an error normally instead of crashing.
- **URL marker validation**: when the URL contains the `<URL not exist>` marker (injected during the agent generation phase), the case fails immediately without sending a request.
- **Excel column validation**: single-API sheets require a `TestID` column and business-flow sheets require a `StepID` column; a missing column raises a `ValueError` and terminates with exit code 2.

For exit codes, see [Configuration & CLI Reference](./configuration.en.md#exit-codes).
