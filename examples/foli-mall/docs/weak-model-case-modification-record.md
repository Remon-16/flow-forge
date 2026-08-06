# 弱模型生成用例修改记录

> 本文记录同一批用例从 AI 原始输出到修正的过程。示例中的原始输出由本地部署的小参数模型 Qwen3-8B-Q4_K_M 生成；agent/ 流水线的工程约束（文档分批、上下文压缩、输出校验）可以减少问题，但不能完全弥补模型能力的不足，修正效果与所用模型的能力直接相关。素材取自 [raw/](../raw/) 的两个 Excel，目标系统为 foli-mall。

## 案例一：退货申请单接口

**AI 原始输出**：

```yaml
POST /api/returns
请求体: {"order_id": "12345", "reason": "defective",
         "return_type": "refund", "evidence_images": ["img1.jpg"]}
期望:  200，断言 $.data.order_id == "12345"
```

**对照 foli-mall 契约发现的问题**：

1. `order_id=12345` 在库里不存在，接口会返回 `204001 订单不存在`；
2. 请求体字段名不符：应为 `orderId / returnReason / returnType`；`evidenceImages` 是逗号分隔字符串而非数组；
3. `return_type` 应为整数（0=仅退款，1=退货退款），不是字符串 `"refund"`；
4. 断言字段 `$.data.order_id` 不存在（退货 VO 里是 `id / orderId / returnNo`）。

**修正后（数据交给插件）**：

```yaml
preprocessors:
  - name: return-fixture          # 自动造 COMPLETED 订单 + 退货记录，注入 returnId
    config:
      return_status: 0            # PENDING_REVIEW
      return_type: 1
assert_dict:
  code: '100000'
assert_rules:
  - $.data.id is_not_null
  - $.data.orderId is_not_null
  - $.data.status == 0
```

**插件做了什么**：`return-fixture` 一次 SQL 完成「已完结订单 + 退货单」的造数，把原本需要手工准备的 3~4 张表数据变成 0 秒，并且用例跑完可清理。

## 案例二：退货完整业务链路（标准退货退款流程测试）

**AI 原始输出（5 步）**：登录 `testuser/Test@123` → 创建退货（`orderId=12345`）→ 寄回商品（URL 硬编码 `12345`）→ 查询详情。

**对照业务规则发现的问题**：

1. 账号 `testuser/Test@123` 不存在（种子账号是 `buyer01/buyer123` 等）；
2. 新建退货状态是 `PENDING_REVIEW(0)`，而寄回商品要求 `APPROVED(1)`——**缺了 seller 审批这一步**，整条链路必然 `208002`；
3. URL 硬编码 `12345`，没有用 `inherit` 把上一步的 `returnId` 传下来；
4. 整条链路只用了买家视角，缺 seller/admin 多角色。

**修正后（10 步，含退货完整状态机）**：

```text
Step_Login_Buyer   buyer01/buyer123
Step_CreateReturn  order-fixture 造 COMPLETED 订单 + POST /api/returns → 断言 status=0
Step_Login_Seller  seller01/seller123
Step_Approve       PUT /api/seller/returns/#{returnId}/approve
Step_ShipBack      PUT /api/returns/#{returnId}/ship-back（buyer01）
Step_Login_Seller  seller01
Step_Confirm       PUT /api/seller/returns/#{returnId}/confirm-receipt
Step_InspectPass   PUT /api/seller/returns/#{returnId}/inspect-pass
Step_Verify        GET /api/returns/#{returnId} → 断言 status=6（已退款）
```

**插件做了什么**：`order-fixture` 把订单一步推到 COMPLETED，省去「下单→支付→发货→收货」4 个前置步骤，让用例聚焦在退货状态机本身。人工审核负责补充业务理解，插件负责补齐数据准备。

## 案例三：下单支付链路（正常下单支付流程验证）

**AI 原始输出**：登录 → 查购物车 → 创建订单 → 支付 → 取消 → 收货（隐含假设「下单后是待支付状态」）。

**对照业务规则发现的问题**：foli-mall 的 `POST /api/orders` **创建即扣款并置为 PAID(1)**，`pay` 和 `cancel` 都只接受 `PENDING_PAY(0)`，所以「下单后支付/取消」必返回 `204002`。AI 套用了常见电商状态机，但没有读 foli-mall 的实现。

**修正后**：把「支付」改为负向断言（`204002 订单状态不正确`）；购物车用 `cart-fixture` 保证有选中项；余额边界用 `balance-fixture` 把余额设为 0.01 复现 `205001 余额不足`，跑完再恢复。

## 用例规模与执行结果

对照两个 raw Excel 的全部 91 条单接口用例与 15 个流程 sheet，curated/ 收录 **74 条用例（65 单接口 + 9 业务链路）**，全部按 foli-mall 真实契约修正并端到端执行：**71 通过 + 3 条 foli-mall 缺陷证据用例按预期失败**（缺陷清单见 [foli-mall-bugs-found.md](./foli-mall-bugs-found.md)）。

### 各模块处理情况

| 模块 | raw 单接口数量 | 处理方式 |
|------|--------------|---------|
| 认证（登录/注册/me） | 27 | 按真实账号与断言修正；合并重复（如 TC_LOGIN_POS_002 并入 001）；删除不存在的场景（密码强度校验、用户名黑名单、未登录返回 200003 等） |
| 购物车 | 19 | 按库存校验语义修正；删除单用例无法复现的并发清空场景；保留 2 条缺陷证据用例 |
| 订单 | 25 | 按状态机与断言修正；删除不存在的场景（items 请求体被忽略、无参数校验、无超时机制等）；跨用户详情越权转为业务链路（缺陷证据） |
| 退货 | 20 | 按 DTO 字段与状态机修正；合并重复的正/负向用例 |
| 业务链路 | 15 个 sheet | 9 条：空购物车下单、订单生命周期、退货完整状态机、退货争议仲裁、无效订单 ID、状态不合规操作、禁用账号登录、删除用户后 /me、跨用户订单详情 |

### 插件说明

curated 用例使用 6 个数据库夹具插件（详见 [plugin-guide.md](./plugin-guide.md)），其中 user-fixture 与 product-fixture 负责补充以下前置状态：

- `user-fixture`：注册幂等（predelete + cleanup）、禁用账号（set_status=0 → 201003）、删除用户后访问 /me（delete → 201004）；
- `product-fixture`：库存不足下单（set_stock）、下架商品购物车项删除（set_status=4）、已删除商品列表（set_deleted），后置 cleanup 恢复原值避免污染共享种子商品。

### 关键修正记录

- 无效 ID 用例使用 19 位"全 9"ID 会超出 `Long` 上限导致 HTTP 500，统一改为 18 位有效格式的不存在 ID；
- 固定 ID 造数会在同一用户购物车产生同商品多行，后续 `POST /api/cart` 触发 `selectOne` 冲突；购物车用例改用 buyer02 隔离，避免污染 buyer01 的下单用例；
- `GET /api/orders` 列表按创建时间倒序、同秒排序不稳定，列表用例不再断言 `records[0].status`，订单状态由详情用例覆盖。

### 端到端结论

- 74 用例（65 单接口 + 9 业务链路）：**71 通过、3 条缺陷证据用例按预期失败**。
- 覆盖范围：登录/注册/当前用户、购物车增删改查与边界、下单与库存/余额边界、订单详情与分页、pay/cancel/receive 状态机正负向、退货完整状态机、退货争议仲裁、禁用账号登录、删除用户后 /me、无效订单 ID、跨用户订单详情。
- HTML 报告：[../curated/report/foli_mall_demo_20260806.html](../curated/report/foli_mall_demo_20260806.html)。
