"""Giao dịch nghiệp vụ viết đúng như backend của ứng dụng (mysql2 -> pymysql), dùng cho C2, C3.

placeOrder    ~ backend/src/services/order.service.ts (FR5, FR6)
withTransaction ~ backend/src/config/db.ts: SET TRANSACTION ISOLATION LEVEL ..., BEGIN, COMMIT, lỗi -> ROLLBACK
"""
import datetime


class AppError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(f"{code}: {msg}")
        self.code = code


def with_transaction(con, fn, isolation="REPEATABLE READ"):
    cur = con.cursor()
    cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
    cur.execute("START TRANSACTION")
    try:
        out = fn(cur)
        cur.execute("COMMIT")
        return out
    except BaseException:
        cur.execute("ROLLBACK")
        raise


def find_customer_with_tier(con, customer_id):
    cur = con.cursor()
    cur.execute("SELECT c.id, c.total_spent, t.discount_pct FROM customers c "
                "JOIN membership_tiers t ON t.id = c.tier_id WHERE c.id = %s", (customer_id,))
    return cur.fetchone()


def place_order(con, customer_id, items, address, reserve="version", profile=None):
    """items: list of dict(variant_id, location_id, quantity).

    reserve = "version": optimistic locking như app (đọc version rồi UPDATE ... AND version = ?)
    reserve = "cond":    cập nhật có điều kiện, không dùng version (InnoDB khóa dòng, giao dịch sau chờ)
    """
    profile = profile or find_customer_with_tier(con, customer_id)

    def body(cur):
        its = sorted(items, key=lambda i: i["variant_id"])  # tránh deadlock như app
        ids = [i["variant_id"] for i in its]
        cur.execute("SELECT v.id, v.price, p.is_limited FROM product_variants v JOIN products p ON p.id = v.product_id "
                    f"WHERE v.id IN ({','.join(['%s'] * len(ids))}) AND v.status = 'active'", ids)
        vmap = {r["id"]: r for r in cur.fetchall()}
        subtotal = 0
        for it in its:
            if it["variant_id"] not in vmap:
                raise AppError("NOT_FOUND")
            subtotal += int(vmap[it["variant_id"]]["price"]) * it["quantity"]
        discount = round(subtotal * float(profile["discount_pct"]) / 100)
        total = max(0, subtotal - discount)
        units = {}
        for idx, it in enumerate(its):
            v = vmap[it["variant_id"]]
            if v["is_limited"]:
                cur.execute("SELECT id, serial_no FROM edition_units WHERE variant_id = %s AND status = 'available' "
                            "ORDER BY id ASC LIMIT 1 FOR UPDATE", (v["id"],))
                u = cur.fetchone()
                if not u:
                    raise AppError("EDITION_SOLD_OUT")
                units[idx] = u["id"]
            if reserve == "version":
                cur.execute("SELECT qty_on_hand, qty_reserved, version FROM inventory "
                            "WHERE variant_id = %s AND location_id = %s LIMIT 1", (v["id"], it["location_id"]))
                inv = cur.fetchone()
                if not inv or inv["qty_on_hand"] - inv["qty_reserved"] < it["quantity"]:
                    raise AppError("OUT_OF_STOCK")
                n = cur.execute("UPDATE inventory SET qty_reserved = qty_reserved + %s, version = version + 1 "
                                "WHERE variant_id = %s AND location_id = %s AND version = %s "
                                "AND (qty_on_hand - qty_reserved) >= %s",
                                (it["quantity"], v["id"], it["location_id"], inv["version"], it["quantity"]))
                if n == 0:
                    raise AppError("VERSION_CONFLICT")
            else:
                n = cur.execute("UPDATE inventory SET qty_reserved = qty_reserved + %s, version = version + 1 "
                                "WHERE variant_id = %s AND location_id = %s AND (qty_on_hand - qty_reserved) >= %s",
                                (it["quantity"], v["id"], it["location_id"], it["quantity"]))
                if n == 0:
                    raise AppError("OUT_OF_STOCK")
        cur.execute("INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address, delivery_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", (customer_id, subtotal, discount, total, address, None))
        oid = cur.lastrowid
        for idx, it in enumerate(its):
            cur.execute("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price, customization) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (oid, it["variant_id"], it["location_id"], it["quantity"], vmap[it["variant_id"]]["price"], None))
            if idx in units:
                cur.execute("UPDATE edition_units SET order_item_id = %s, status = 'reserved' "
                            "WHERE id = %s AND status = 'available'", (cur.lastrowid, units[idx]))
        deposit = round(total * 0.5)
        today = datetime.date.today()
        cur.execute("INSERT INTO payments (order_id, type, amount, due_date, status) VALUES (%s, 'deposit', %s, %s, 'pending')",
                    (oid, deposit, today))
        cur.execute("INSERT INTO payments (order_id, type, amount, due_date, status) VALUES (%s, 'final', %s, %s, 'pending')",
                    (oid, total - deposit, today + datetime.timedelta(days=30)))
        return oid

    return with_transaction(con, body)


def place_order_proc(con, customer_id, variant_id, location_id, qty, address):
    cur = con.cursor()
    cur.execute("CALL sp_place_order(%s, %s, %s, %s, %s, @oid)", (customer_id, variant_id, location_id, qty, address))
    cur.execute("SELECT @oid AS oid")
    return cur.fetchone()["oid"]
