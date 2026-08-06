# foli-mall 接口实测发现的业务缺陷

> 以下缺陷均由 flow-forge 执行器对 foli-mall（后端 + H2 内存库）实测确认。curated 用例集中对应的用例**保留"正确期望"的断言**，运行结果为预期失败，并在用例 `remark` 中标注 `BugEvidence`，作为"API 测试能发现缺陷"的展示证据。缺陷本身未修改 foli-mall。

## Bug 1：加购不校验数量与库存（addToCart）

- **位置**：`FmCartItemServiceImpl.addToCart`
- **现象**：购物车加购（`POST /api/cart`）只校验 `库存 > 0`，不校验 `数量 ≤ 库存`。quantity=100（库存 50）仍返回 `100000 成功`。
- **证据用例**：`TC_CART_POST_NEG_001`（期望 `203002 库存不足`，实测 `100000`）。
- **期望行为**：与下单一致，加购数量超过库存应返回 `203002`。

## Bug 2：更新购物车数量不校验库存（updateCartItem）

- **位置**：`FmCartItemServiceImpl.updateCartItem`
- **现象**：`PUT /api/cart/{id}` 把数量改为远超库存（如 100，库存 50）仍返回 `100000`，与 `POST /api/cart` 的库存校验语义不一致。
- **证据用例**：`TC_CART_ID_PUT_NEG_004`（期望 `203002 库存不足`，实测 `100000`）。
- **期望行为**：更新数量时应校验 `数量 ≤ 库存`。

## Bug 3：订单详情缺少属主校验（getOrderDetail 越权读取）

- **位置**：`FmOrderServiceImpl.getOrderDetail`（`OrderController.getOrderDetail` 仅要求登录）
- **现象**：buyer01 登录后可直接 `GET /api/orders/{buyer02的订单ID}` 读取完整订单详情（HTTP 200 + `100000`，含收货人、金额、商品明细）。
- **证据用例**：`FLOW_ORDER_CROSS_USER_DETAIL` 最后一步（期望 `200003 无权执行此操作`，实测 `100000`）。
- **期望行为**：非属主且非卖家/管理员应返回 `200003` 或 `204001`。

## Bug 4：退货详情缺少属主校验（getReturnDetail 越权读取）

- **位置**：`FmReturnRefundServiceImpl.getReturnDetail`
- **现象**：买家 A 创建的退货单，买家 B 可 `GET /api/returns/{id}` 读取完整详情（HTTP 200 + `100000`，含 userId、订单号、退款金额）。
- **备注**：raw Excel 中没有跨用户退货详情场景，curated 用例集未包含对应断言用例。

## 说明

- 上述用例在端到端报告中显示为"失败"，这是**预期行为**，用于向用户展示自动化测试的价值：这些缺陷若不写断言，手工回归很难发现。
- 修复建议（仅记录，不改 foli-mall）：`addToCart`/`updateCartItem` 增加数量与库存校验；`getOrderDetail`/`getReturnDetail` 增加属主/角色校验。
