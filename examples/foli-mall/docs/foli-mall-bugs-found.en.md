# foli-mall bugs found through API testing

> The following defects were confirmed by running the flow-forge executor against foli-mall (backend + in-memory H2). The corresponding curated cases keep their **correct expectations** so the runs fail as expected; each case is tagged `BugEvidence` in its `remark` as proof that API testing can surface real defects. foli-mall itself was not modified.

## Bug 1: addToCart does not validate quantity against stock

- **Location**: `FmCartItemServiceImpl.addToCart`
- **Behavior**: `POST /api/cart` only checks `stock > 0`; it never checks `quantity <= stock`. Adding quantity=100 to a product with stock=50 still returns `100000 success`.
- **Evidence case**: `TC_CART_POST_NEG_001` (expects `203002 insufficient stock`, actual `100000`).
- **Expected**: quantity over stock should return `203002`, consistent with order creation.

## Bug 2: updateCartItem does not validate stock

- **Location**: `FmCartItemServiceImpl.updateCartItem`
- **Behavior**: `PUT /api/cart/{id}` accepts a quantity far above stock (e.g., 100 with stock 50) and returns `100000`, inconsistent with the stock check in `POST /api/cart`.
- **Evidence case**: `TC_CART_ID_PUT_NEG_004` (expects `203002 insufficient stock`, actual `100000`).
- **Expected**: quantity updates should validate `quantity <= stock`.

## Bug 3: getOrderDetail has no ownership check (unauthorized read)

- **Location**: `FmOrderServiceImpl.getOrderDetail` (`OrderController.getOrderDetail` only requires login)
- **Behavior**: buyer01 can `GET /api/orders/{buyer02's order id}` and read the full order detail (HTTP 200 + `100000`, including receiver info, amount, and line items).
- **Evidence case**: the last step of `FLOW_ORDER_CROSS_USER_DETAIL` (expects `200003 access denied`, actual `100000`).
- **Expected**: non-owners (unless seller/admin) should receive `200003` or `204001`.

## Bug 4: getReturnDetail has no ownership check

- **Location**: `FmReturnRefundServiceImpl.getReturnDetail`
- **Behavior**: a return created by buyer A can be read in full by buyer B via `GET /api/returns/{id}` (HTTP 200 + `100000`, including userId, order number, and refund amount).
- **Note**: the raw Excel files contain no cross-user return-detail scenario, so the curated suite does not include a dedicated assertion for this defect.

## Notes

- These cases are reported as "failed" in the end-to-end report **on purpose**, demonstrating the value of automated API testing: such defects are easy to miss in manual regression.
- Suggested fixes (recorded only; foli-mall unchanged): add quantity/stock validation to `addToCart`/`updateCartItem`, and ownership/role checks to `getOrderDetail`/`getReturnDetail`.
