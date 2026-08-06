# 前置数据 DB 插件指南

flow-forge 的 Python 执行器内置 6 个数据库前置数据插件（位于 `python/processors/builtin/db/`），用于为「需要指定前置状态」的用例一步补齐数据。它们复用共享模块 `_fixtures_common.py`（建单 / 删单 / 建退货等），SQL 使用 SQLAlchemy 通用写法，默认连接 foli-mall 的 H2 内存库，`db_url` 切换为 MySQL 等数据库同样可用。

> 插件均为 `BaseDBPlugin` 子类，自动注册为 Pre/Post 处理器；用例中通过 `preprocessors` / `postprocessors` 引用，支持与登录 `#{userParamName}`、「插件上插件」（多处理器叠加）组合使用。
> 注意：foli-mall 使用 MyBatis-Plus 逻辑删除（`is_delete`），插件的查询 / 插入均已遵循 `is_delete=0` 约定。

## 1. order-fixture — 订单前置数据

**功能**：直接向 `fm_order` + `fm_order_item` 创建一条指定状态（0–5）的测试订单，并把 `orderId` 注入请求体。适用于需要「已完成 / 已支付 / 已发货 / 待支付 / 已取消」订单的用例。

**配置字段**（env 或 case 级，case 覆盖 env）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `test_buyer_id` | str/int | 1000000000000000007 | 无登录用户时的买家 ID（有登录用户时自动取当前用户） |
| `test_store_id` | str/int | 1000000000000002001 | 店铺 ID |
| `test_product_id` | str/int | 1000000000000003001 | 商品 ID |
| `order_status` | int | 4 | 订单状态：0=待支付 1=已支付 2=已发货 3=已收货 4=已完成 5=已取消 |
| `quantity` | int | 1 | 订单明细数量 |
| `total_amount` | float | 商品价格 | 订单总金额覆盖 |
| `receiver_name/phone/address` | str | 测试值 | 收货人信息 |
| `order_id` | int | 自动生成 | **固定 ID**（幂等：先删旧记录再插入），便于 URL 使用字面 ID |
| `cleanup` | bool | false | 后置处理器删除该测试订单（需同时在 postprocessors 配置 cleanup: true） |

**YAML 示例**：

```yaml
preprocessors:
  - name: order-fixture
    config:
      order_status: 4        # 已完成订单（退货前置）
postprocessors:
  - name: order-fixture
    config:
      cleanup: true
```

**适用用例**：退货创建、订单 pay/cancel/receive 状态机负向、订单详情正向等。

## 2. cart-fixture — 购物车前置数据

**功能**：按 `mode` 操作 `fm_cart_item`：

- `add`：新增购物车项；同商品（未逻辑删除）已存在时累加数量（遵循 foli-mall 语义）。
- `clear`：物理清空指定用户的全部购物车行（含历史逻辑删除残留），彻底重置状态。
- `ensure`：确保至少一个「选中项」（selected=1 且 is_delete=0），否则插入默认商品。

**配置字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `test_buyer_id` | str/int | 1000000000000000007 | 买家 ID（有登录用户时自动取当前用户） |
| `mode` | str | ensure | `add` / `clear` / `ensure` |
| `product_id` | int | 1000000000000003001 | 商品 ID |
| `quantity` | int | 1 | 数量（add/ensure 使用） |
| `selected` | int | 1 | 是否选中（add 使用） |
| `inject_cart_item_id` | bool | false | 把 `cartItemId` 注入请求体 |
| `inject_selected_count` | bool | false | 把 `cartSelectedCount` 注入请求体 |

**YAML 示例**：

```yaml
preprocessors:
  - name: cart-fixture
    config:
      mode: ensure
```

**适用用例**：下单流程、购物车为空下单失败（mode: clear）、购物车列表 / 删除等。

## 3. return-fixture — 退货前置数据

**功能**：先创建一条 COMPLETED(4) 订单（可关闭），再插入一条指定状态（0–7）的 `fm_return_refund` 记录，并把 `returnId` 注入请求体。适用于 ship-back / 买家争议 / 退货详情等「需要已有退货记录」的用例。

**配置字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `test_buyer_id` / `test_store_id` / `test_product_id` | - | 种子 ID | 同 order-fixture |
| `return_status` | int | 0 | 退货状态：0=待审核 1=已通过 2=已拒绝 3=买家退回中 4=卖家已收货 6=已退款 7=争议中 |
| `return_type` | int | 1 | 0=仅退款 1=退货退款 |
| `return_reason` | str | e2e fixture return | 退货原因 |
| `refund_amount` | float | 订单总额 | 退款金额覆盖 |
| `create_order` | bool | true | 是否同时创建 COMPLETED 订单 |
| `order_id` | int | 自动生成 | 固定订单 ID（幂等） |
| `return_id` | int | 自动生成 | **固定退货 ID**（幂等），便于 URL 使用字面 ID |
| `cleanup` | bool | false | 后置删除退货 + 订单 |

**YAML 示例**：

```yaml
preprocessors:
  - name: return-fixture
    config:
      return_status: 2        # 已拒绝（买家争议前置）
      return_id: 9000000000000000009
```

**适用用例**：ship-back 负向（return_status=0/3 期望 208002）、买家争议（return_status=2）、退货详情、退货列表等。

## 4. balance-fixture — 余额前置数据

**功能**：将指定用户余额设为配置值（直接 UPDATE `fm_user.balance`）。适用于「余额不足」与「恢复余额」场景。

**配置字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `test_buyer_id` | str/int | 1000000000000000007 | 买家 ID（有登录用户时自动取当前用户） |
| `balance` | float | 10000 | 目标余额 |

**YAML 示例**：

```yaml
preprocessors:
  - name: balance-fixture
    config:
      balance: 0.01            # 余额不足
```

**适用用例**：余额不足下单失败（期望 205001）、测试后恢复余额（balance=10000）。

## 5. user-fixture — 用户前置数据

**功能**：直接操作 `fm_user`，支持四种模式：

- `predelete`：按 username 物理删除，用于注册用例的幂等前置（避免"用户名已存在"）；
- `create`：插入测试用户（内置密码 `e2e123` 的 BCrypt 哈希常量，balance/role/status 可配，幂等先删后插）；
- `set_status`：禁用/启用账号（0=禁用 1=正常）；
- `delete`：按 username/user_id 删除。

后置 `cleanup` 会删除该测试用户，保证可重复执行。

**配置字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `username` | str | - | 目标用户名（除 user_id 定位外均必填） |
| `user_id` | int | 自动生成 | 固定用户 ID（create 幂等） |
| `password_hash` | str | e2e123 的 BCrypt | 密码哈希（create 使用） |
| `balance` | float | 0 | 余额（create 使用） |
| `role` | int | 0 | 角色：0=买家 1=卖家 2=管理员 |
| `status` | int | 1 | 状态：0=禁用 1=正常 |
| `cleanup` | bool | false | 后置删除该用户 |

**YAML 示例**：

```yaml
preprocessors:
  - name: user-fixture
    config:
      mode: predelete        # 注册前清理同名用户
      username: e2e_user
postprocessors:
  - name: user-fixture
    config:
      cleanup: true
```

**适用用例**：注册幂等（predelete + cleanup）、禁用账号登录（set_status=0 → 201003）、删除用户后访问 /me（delete → 201004）。

## 6. product-fixture — 商品前置数据

**功能**：直接操作 `fm_product`，支持 `set_stock`（库存）、`set_status`（2=上架 4=下架）、`set_deleted`（逻辑删除 is_delete=1）。种子商品被多个用例共享，因此后置 `cleanup` 会**恢复原 stock / status / is_delete**，避免污染其他用例。

**配置字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_url` | str | - | 数据库连接（env 级必填） |
| `product_id` | int | 1000000000000003001 | 商品 ID（env 级可配 `test_product_id`） |
| `stock` | int | 50 | 目标库存（set_stock 使用） |
| `status` | int | 4 | 目标状态：2=上架 4=下架（set_status 使用） |
| `cleanup` | bool | false | 后置恢复原值 |

**YAML 示例**：

```yaml
preprocessors:
  - name: product-fixture
    config:
      mode: set_stock
      stock: 50
postprocessors:
  - name: product-fixture
    config:
      cleanup: true
```

**适用用例**：库存不足下单（set_stock 明确库存）、下架商品购物车项删除（set_status=4）、已删除商品列表（set_deleted）。

## 与两个 raw Excel 的用例映射

| Excel 场景 | 需要的插件 |
|-----------|-----------|
| 购物车加购 / 列表 / 删除 / 更新 | cart-fixture（ensure/add） |
| 创建订单（有选中项） | cart-fixture（ensure） |
| 购物车为空下单失败 | cart-fixture（clear） |
| 余额不足下单失败 | balance-fixture（0.01） |
| 订单 pay/cancel/receive 负向 | order-fixture（order_status=1/2/0） |
| 退货创建（需 COMPLETED 订单） | order-fixture（order_status=4） |
| 退货 ship-back / 争议 / 详情 | return-fixture（return_status 按需） |
| 注册幂等 / 禁用账号 / 删除用户 | user-fixture（predelete/create/set_status/delete） |
| 库存不足下单 / 下架商品 / 已删除商品 | product-fixture（set_stock/set_status/set_deleted） |

## 测试情况

- 单元测试：`python/tests/test_order_fixture_plugin.py`、`test_cart_fixture_plugin.py`、`test_return_fixture_plugin.py`、`test_balance_fixture_plugin.py`、`test_user_fixture_plugin.py`、`test_product_fixture_plugin.py`（mock DB，不触真实库、不调 LLM）；全量 `python -m pytest tests/ -q` 通过。
- 端到端：74 用例（65 单接口 + 9 业务链路），71 通过 + 3 条 foli-mall 缺陷证据用例按预期失败（详见 [foli-mall-bugs-found.md](./foli-mall-bugs-found.md)），运行结论见 [weak-model-case-modification-record.md](./weak-model-case-modification-record.md)，报告见 [../curated/report/](../curated/report/)。
