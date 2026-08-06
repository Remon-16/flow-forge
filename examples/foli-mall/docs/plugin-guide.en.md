# Database fixture plugin guide

The flow-forge Python executor ships six database fixture plugins (in `python/processors/builtin/db/`) that prepare the prerequisite data a case needs in a single step. They share the `_fixtures_common.py` module (create/delete orders, create returns, etc.). The SQL is written with SQLAlchemy in a generic way and targets the foli-mall H2 in-memory database by default; switching `db_url` to MySQL or another database works the same way.

> The plugins are subclasses of `BaseDBPlugin` and register themselves as pre/post processors. Cases reference them through `preprocessors` / `postprocessors`, and they can be combined with login placeholders (`#{userParamName}`) and stacked with other processors.
> Note: foli-mall uses MyBatis-Plus logical deletion (`is_delete`); all queries/inserts follow the `is_delete=0` convention.

## 1. order-fixture — order prerequisite data

**Purpose**: create a test order with a given status (0–5) directly in `fm_order` + `fm_order_item` and inject `orderId` into the request. For cases that need a completed/paid/shipped/pending/cancelled order.

**Config fields** (env-level or case-level; case overrides env):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `test_buyer_id` | str/int | 1000000000000000007 | Buyer ID when no logged-in user (otherwise the current user) |
| `test_store_id` | str/int | 1000000000000002001 | Store ID |
| `test_product_id` | str/int | 1000000000000003001 | Product ID |
| `order_status` | int | 4 | Order status: 0=pending pay 1=paid 2=shipped 3=received 4=completed 5=cancelled |
| `quantity` | int | 1 | Order item quantity |
| `total_amount` | float | product price | Overrides the order total |
| `receiver_name/phone/address` | str | test values | Receiver info |
| `order_id` | int | auto | **Fixed ID** (idempotent: deletes old records first) so URLs can use a literal ID |
| `cleanup` | bool | false | Post-processor deletes the test order (needs `cleanup: true` in `postprocessors`) |

**YAML example**:

```yaml
preprocessors:
  - name: order-fixture
    config:
      order_status: 4        # completed order (prerequisite for returns)
postprocessors:
  - name: order-fixture
    config:
      cleanup: true
```

**Typical use**: return creation, negative pay/cancel/receive state-machine cases, order-detail positive cases, etc.

## 2. cart-fixture — cart prerequisite data

**Purpose**: manipulate `fm_cart_item` by `mode`:

- `add`: add a cart item; if the same product (not logically deleted) exists, quantities accumulate (foli-mall semantics).
- `clear`: physically clear all cart rows of the given user (including logical-deletion leftovers) for a clean slate.
- `ensure`: make sure at least one "selected" item exists (selected=1 and is_delete=0), inserting the default product otherwise.

**Config fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `test_buyer_id` | str/int | 1000000000000000007 | Buyer ID (current user when logged in) |
| `mode` | str | ensure | `add` / `clear` / `ensure` |
| `product_id` | int | 1000000000000003001 | Product ID |
| `quantity` | int | 1 | Quantity (used by add/ensure) |
| `selected` | int | 1 | Whether selected (used by add) |
| `inject_cart_item_id` | bool | false | Inject `cartItemId` into the request body |
| `inject_selected_count` | bool | false | Inject `cartSelectedCount` into the request body |

**YAML example**:

```yaml
preprocessors:
  - name: cart-fixture
    config:
      mode: ensure
```

**Typical use**: order creation, empty-cart order failure (mode: clear), cart list/delete, etc.

## 3. return-fixture — return prerequisite data

**Purpose**: create a COMPLETED(4) order (optional) and insert an `fm_return_refund` record with a given status (0–7), injecting `returnId` into the request. For cases that need an existing return record (ship-back, buyer dispute, return detail).

**Config fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `test_buyer_id` / `test_store_id` / `test_product_id` | - | seed IDs | same as order-fixture |
| `return_status` | int | 0 | Return status: 0=pending review 1=approved 2=rejected 3=buyer shipping 4=seller received 6=refunded 7=disputed |
| `return_type` | int | 1 | 0=refund only 1=return and refund |
| `return_reason` | str | e2e fixture return | Return reason |
| `refund_amount` | float | order total | Refund amount override |
| `create_order` | bool | true | Whether to also create a COMPLETED order |
| `order_id` | int | auto | Fixed order ID (idempotent) |
| `return_id` | int | auto | **Fixed return ID** (idempotent) for literal IDs in URLs |
| `cleanup` | bool | false | Post-processor deletes the return + order |

**YAML example**:

```yaml
preprocessors:
  - name: return-fixture
    config:
      return_status: 2        # rejected (prerequisite for buyer dispute)
      return_id: 9000000000000000009
```

**Typical use**: negative ship-back (return_status=0/3 expecting 208002), buyer dispute (return_status=2), return detail/list, etc.

## 4. balance-fixture — balance prerequisite data

**Purpose**: set a user's balance to a configured value (direct UPDATE on `fm_user.balance`). For "insufficient balance" and "restore balance" scenarios.

**Config fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `test_buyer_id` | str/int | 1000000000000000007 | Buyer ID (current user when logged in) |
| `balance` | float | 10000 | Target balance |

**YAML example**:

```yaml
preprocessors:
  - name: balance-fixture
    config:
      balance: 0.01            # insufficient balance
```

**Typical use**: order creation failing with insufficient balance (expect 205001), restoring the balance afterwards (balance=10000).

## 5. user-fixture — user prerequisite data

**Purpose**: manipulate `fm_user` directly with four modes:

- `predelete`: physically delete by username, an idempotent precondition for register cases (avoids "username already exists");
- `create`: insert a test user (a built-in BCrypt hash constant for password `e2e123`; balance/role/status configurable; idempotent delete-then-insert);
- `set_status`: disable/enable an account (0=disabled 1=enabled);
- `delete`: delete by username/user_id.

The post `cleanup` deletes the test user so cases stay repeatable.

**Config fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `username` | str | - | Target username (required unless locating by user_id) |
| `user_id` | int | auto-generated | Fixed user ID (idempotent for create) |
| `password_hash` | str | BCrypt of e2e123 | Password hash (used by create) |
| `balance` | float | 0 | Balance (used by create) |
| `role` | int | 0 | Role: 0=buyer 1=seller 2=admin |
| `status` | int | 1 | Status: 0=disabled 1=enabled |
| `cleanup` | bool | false | Delete the user afterwards |

**YAML example**:

```yaml
preprocessors:
  - name: user-fixture
    config:
      mode: predelete        # clean up the same username before register
      username: e2e_user
postprocessors:
  - name: user-fixture
    config:
      cleanup: true
```

**Typical use**: idempotent register (predelete + cleanup), disabled-account login (set_status=0 → 201003), and /me after user deletion (delete → 201004).

## 6. product-fixture — product prerequisite data

**Purpose**: manipulate `fm_product` directly with `set_stock` (stock), `set_status` (2=on shelf 4=off shelf), and `set_deleted` (logical delete, is_delete=1). Seed products are shared across cases, so the post `cleanup` **restores the original stock / status / is_delete** to avoid polluting other cases.

**Config fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `db_url` | str | - | Database connection (required at env level) |
| `product_id` | int | 1000000000000003001 | Product ID (env-level `test_product_id` also accepted) |
| `stock` | int | 50 | Target stock (used by set_stock) |
| `status` | int | 4 | Target status: 2=on shelf 4=off shelf (used by set_status) |
| `cleanup` | bool | false | Restore original values afterwards |

**YAML example**:

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

**Typical use**: insufficient-stock order creation (set_stock with explicit stock), deleting a cart item of an off-shelf product (set_status=4), and cart listing with a deleted product (set_deleted).

## Mapping to the two raw Excel files

| Excel scenario | Needed plugin |
|----------------|---------------|
| Cart add/list/delete/update | cart-fixture (ensure/add) |
| Create order (with selected items) | cart-fixture (ensure) |
| Empty-cart order failure | cart-fixture (clear) |
| Insufficient-balance order failure | balance-fixture (0.01) |
| Negative pay/cancel/receive | order-fixture (order_status=1/2/0) |
| Return creation (needs COMPLETED order) | order-fixture (order_status=4) |
| Return ship-back / dispute / detail | return-fixture (return_status as needed) |
| Idempotent register / disabled account / deleted user | user-fixture (predelete/create/set_status/delete) |
| Insufficient stock / off-shelf product / deleted product | product-fixture (set_stock/set_status/set_deleted) |

## Testing

- Unit tests: `python/tests/test_order_fixture_plugin.py`, `test_cart_fixture_plugin.py`, `test_return_fixture_plugin.py`, `test_balance_fixture_plugin.py`, `test_user_fixture_plugin.py`, and `test_product_fixture_plugin.py` (mocked DB, no real database, no LLM calls); the full `python -m pytest tests/ -q` suite passes.
- End-to-end: 74 cases (65 single-API + 9 business flows); 71 pass and 3 foli-mall bug-evidence cases fail as expected (see [foli-mall-bugs-found.md](./foli-mall-bugs-found.md)); see [weak-model-case-modification-record.md](./weak-model-case-modification-record.md) and the report in [../curated/report/](../curated/report/).
