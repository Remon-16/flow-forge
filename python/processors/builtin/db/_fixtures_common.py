"""数据库测试数据夹具的共享工具函数。
Shared helper functions for DB test-data fixtures.

这些函数被 order-fixture / cart-fixture / return-fixture / balance-fixture
四个内置插件复用，避免重复实现建单、删单、建退货等逻辑。
These helpers are shared by the order-fixture / cart-fixture / return-fixture /
balance-fixture built-in plugins to avoid duplicating order/return creation logic.
"""

import logging
import time
from datetime import datetime
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

from i18n import _

# foli-mall 种子数据固定 ID（与 DataInitializer 一致）
# Fixed seed IDs (consistent with foli-mall DataInitializer)
SEED_BUYER_ID = 1000000000000000007   # buyer01
SEED_STORE_ID = 1000000000000002001   # store1 (Digital Pioneer Store)
SEED_PRODUCT_ID = 1000000000000003001 # product1 (iPhone 15 Pro Max)


def resolve_user_id(current_user: Any, default: Any = None) -> Any:
    """从登录用户配置中提取用户 ID（兼容 id / user_id 两种键名）。
    Extract the user id from a logged-in user config (accepts both id and user_id keys).

    env 文件中用户账号通常写作 ``id:``（如 buyer01.id），而部分旧配置使用
    ``user_id:``；两种都支持，避免插件静默回退到默认买家。
    Env user accounts usually use ``id:`` (e.g. buyer01.id), while some legacy
    configs use ``user_id:``; both are accepted so plugins do not silently
    fall back to the default buyer.
    """
    if isinstance(current_user, dict):
        for key in ("user_id", "id"):
            if current_user.get(key) is not None:
                return current_user[key]
    return default


def gen_id(offset: int = 0) -> int:
    """生成与 return-order-db 一致的唯一 ID。
    Generate a unique ID consistent with return-order-db."""
    return (int(time.time() * 1000000) + offset) % (10 ** 15)


def now_str() -> str:
    """返回当前时间字符串。Return the current timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_product(conn: Any, product_id: int) -> Optional[Tuple[str, str, Any]]:
    """查询商品快照 (name, main_image, price)；不存在时返回 None。
    Query a product snapshot (name, main_image, price); None if missing."""
    from sqlalchemy import text

    rows = conn.execute(
        text("SELECT name, main_image, price FROM fm_product WHERE id = :pid AND is_delete = 0"),
        {"pid": product_id},
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    return row[0], row[1] or "", row[2]


def insert_order(
    conn: Any,
    *,
    order_id: int,
    buyer_id: int,
    store_id: int,
    product_id: int,
    quantity: int = 1,
    total_amount: Optional[float] = None,
    status: int = 4,
    receiver_name: str = "",
    receiver_phone: str = "",
    receiver_address: str = "",
) -> Tuple[str, str, str, Any]:
    """插入一条订单及一条订单明细，返回 (order_no, product_name, product_image, price)。
    Insert one order and one line item; return (order_no, product_name, product_image, price)."""
    from sqlalchemy import text

    now = now_str()
    product = read_product(conn, product_id)
    if product:
        product_name, product_image, price = product
    else:
        # 商品不存在时使用默认值，保证用例可继续 / Fallback defaults when product is missing
        logger.warning(_("fixtures_common.product_not_found", product_id=product_id))
        product_name, product_image, price = "Test Product", "", 99.99

    final_amount = float(total_amount) if total_amount is not None else float(price)
    order_no = f"TEST{order_id % (10 ** 12):012d}"

    conn.execute(
        text(
            "INSERT INTO fm_order (id, order_no, user_id, store_id, "
            "total_amount, status, receiver_name, receiver_phone, receiver_address, is_delete, "
            "create_time, edit_time, update_time) "
            "VALUES (:id, :order_no, :user_id, :store_id, "
            ":total_amount, :status, :receiver_name, :receiver_phone, :receiver_address, 0, "
            ":now, :now, :now)"
        ),
        {
            "id": order_id,
            "order_no": order_no,
            "user_id": buyer_id,
            "store_id": store_id,
            "total_amount": final_amount,
            "status": status,
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "receiver_address": receiver_address,
            "now": now,
        },
    )
    conn.execute(
        text(
            "INSERT INTO fm_order_item (id, order_id, product_id, "
            "product_name, product_image, price, quantity, is_delete, "
            "create_time, edit_time, update_time) "
            "VALUES (:id, :order_id, :product_id, "
            ":product_name, :product_image, :price, :quantity, 0, "
            ":now, :now, :now)"
        ),
        {
            "id": order_id + 1,
            "order_id": order_id,
            "product_id": product_id,
            "product_name": product_name,
            "product_image": product_image,
            "price": final_amount,
            "quantity": quantity,
            "now": now,
        },
    )
    return order_no, product_name, product_image, final_amount


def delete_order(conn: Any, order_id: int) -> None:
    """删除订单及其明细。Delete an order and its line items."""
    from sqlalchemy import text

    conn.execute(text("DELETE FROM fm_order_item WHERE order_id = :oid"), {"oid": order_id})
    conn.execute(text("DELETE FROM fm_order WHERE id = :oid"), {"oid": order_id})


def insert_return(
    conn: Any,
    *,
    return_id: int,
    order_id: int,
    buyer_id: int,
    store_id: int,
    return_reason: str = "",
    return_type: int = 1,
    refund_amount: Optional[float] = None,
    status: int = 0,
) -> str:
    """插入一条退货退款记录，返回 return_no。
    Insert a return/refund record; return its return_no."""
    from sqlalchemy import text

    now = now_str()
    amount = float(refund_amount) if refund_amount is not None else 0.0
    return_no = f"RT{now[:10].replace('-', '')}{return_id % 1000000:06d}"
    conn.execute(
        text(
            "INSERT INTO fm_return_refund (id, return_no, order_id, user_id, store_id, "
            "return_reason, return_type, refund_amount, status, is_delete, "
            "create_time, edit_time, update_time) "
            "VALUES (:id, :return_no, :order_id, :user_id, :store_id, "
            ":return_reason, :return_type, :refund_amount, :status, 0, "
            ":now, :now, :now)"
        ),
        {
            "id": return_id,
            "return_no": return_no,
            "order_id": order_id,
            "user_id": buyer_id,
            "store_id": store_id,
            "return_reason": return_reason,
            "return_type": return_type,
            "refund_amount": amount,
            "status": status,
            "now": now,
        },
    )
    return return_no


def delete_return(conn: Any, return_id: int) -> None:
    """删除一条退货退款记录。Delete a return/refund record."""
    from sqlalchemy import text

    conn.execute(text("DELETE FROM fm_return_refund WHERE id = :rid"), {"rid": return_id})
