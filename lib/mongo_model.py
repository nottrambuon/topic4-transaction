"""Mô hình MongoDB của ứng dụng: 16 bảng -> 8 collection; hai giao dịch nghiệp vụ như backend.

| Bảng MySQL                                                         | Collection     |
|--------------------------------------------------------------------|----------------|
| orders, order_items, payments                                      | orders (items[], payments[] nhúng) |
| products, product_variants, brands, categories, materials, variant_materials | variants (thông tin sản phẩm nhúng) |
| inventory                                                          | inventory (1 document / biến thể x địa điểm, có version) |
| edition_units                                                      | edition_units  |
| users, customers, membership_tiers, locations                      | giữ nguyên tên |
| reviews                                                            | (không dùng trong thực nghiệm) |
"""
import datetime

from bson import ObjectId
from pymongo import ReturnDocument

INVENTORY_RULE = {"$expr": {"$and": [{"$gte": ["$qty_on_hand", 0]}, {"$gte": ["$qty_reserved", 0]},
                                     {"$lte": ["$qty_reserved", "$qty_on_hand"]}]}}

COLLECTIONS = ["membership_tiers", "users", "customers", "variants", "locations", "inventory", "edition_units", "orders"]


class AppError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(f"{code}: {msg}")
        self.code = code


def inv_id(variant_id, location_id):
    return f"{variant_id}:{location_id}"


def reset(db):
    for name in db.list_collection_names():
        db.drop_collection(name)
    for name in COLLECTIONS:
        if name == "inventory":
            db.create_collection(name, validator=INVENTORY_RULE)
        else:
            db.create_collection(name)
    db.membership_tiers.insert_many([
        dict(_id=1, name="Silver", min_spent=0, discount_pct=0),
        dict(_id=2, name="Gold", min_spent=150_000_000, discount_pct=5),
        dict(_id=3, name="Black", min_spent=500_000_000, discount_pct=10)])
    db.users.insert_many([
        dict(_id=1, email="admin@luxe.vn", full_name="Quản trị viên", role="admin"),
        dict(_id=2, email="lan@luxe.vn", full_name="Nguyễn Thị Lan", role="sales"),
        dict(_id=3, email="minh@luxe.vn", full_name="Đỗ Quang Minh", role="sales"),
        dict(_id=4, email="an@mail.vn", full_name="Trần Văn An", role="customer"),
        dict(_id=5, email="binh@mail.vn", full_name="Lê Thị Bình", role="customer"),
        dict(_id=6, email="chi@mail.vn", full_name="Phạm Minh Chi", role="customer")])
    db.customers.insert_many([
        dict(_id=1, user_id=4, tier_id=2, address="12 Nguyễn Huệ, Quận 1", city="Hồ Chí Minh", total_spent=420_000_000),
        dict(_id=2, user_id=5, tier_id=1, address="5 Tràng Tiền", city="Hà Nội", total_spent=60_000_000),
        dict(_id=3, user_id=6, tier_id=1, address="88 Võ Văn Tần, Quận 3", city="Hồ Chí Minh", total_spent=0)])

    def variant(vid, name, brand, category, sku, size, finish, price, lead=0, limited=False, mto=False, materials=()):
        return dict(_id=vid, sku=sku, size=size, finish=finish, price=price, lead_time_days=lead, status="active",
                    product=dict(name=name, brand=brand, category=category, is_limited=limited, is_made_to_order=mto),
                    materials=[dict(name=m, portion=p) for m, p in materials])
    db.variants.insert_many([
        variant(101, "Sofa Lawson", "Minotti", "Sofa", "LAWSON-240-GRY", "240x100x85 cm", "Xám tro", 480_000_000,
                materials=[("Da Nappa", 80), ("Gỗ óc chó", 20)]),
        variant(102, "Sofa Lawson", "Minotti", "Sofa", "LAWSON-300-BEI", "300x105x85 cm", "Be cát", 620_000_000),
        variant(201, "Ghế Archibald Gran Comfort", "Poltrona Frau", "Ghế bành", "ARCHI-LTD-CGN", "90x95x100 cm",
                "Cognac", 950_000_000, limited=True, materials=[("Da Nappa", 90), ("Đồng thau", 10)]),
        variant(301, "Bàn trà Marmo", "Baxter", "Bàn trà", "MARMO-120-CAL", "120x60x35 cm", "Calacatta",
                380_000_000, lead=60, mto=True, materials=[("Đá Calacatta", 85), ("Đồng thau", 15)]),
        variant(401, "Bàn ăn Venice", "Minotti", "Bàn ăn", "VENICE-220-WAL", "220x100x75 cm", "Óc chó",
                290_000_000, materials=[("Gỗ óc chó", 100)])])
    db.locations.insert_many([
        dict(_id=1, name="Showroom Quận 1", type="showroom", city="Hồ Chí Minh"),
        dict(_id=2, name="Showroom Hoàn Kiếm", type="showroom", city="Hà Nội"),
        dict(_id=3, name="Kho Bình Dương", type="warehouse", city="Bình Dương")])
    db.inventory.insert_many([
        dict(_id=inv_id(v, l), variant_id=v, location_id=l, qty_on_hand=h, qty_reserved=r, version=0)
        for v, l, h, r in [(101, 1, 2, 0), (101, 3, 6, 0), (102, 1, 1, 0), (102, 3, 3, 1),
                           (201, 1, 2, 0), (401, 1, 1, 0), (401, 3, 4, 0)]])
    db.edition_units.insert_many([
        dict(_id=7, variant_id=201, serial_no="07/50", status="available", order_id=None),
        dict(_id=8, variant_id=201, serial_no="08/50", status="available", order_id=None)])
    now = datetime.datetime.now()
    db.orders.insert_one(dict(
        _id=1, customer_id=1, sales_user_id=2, order_date=now, status="confirmed",
        subtotal=620_000_000, discount=31_000_000, total=589_000_000, shipping_address="12 Nguyễn Huệ, Quận 1",
        items=[dict(line=1, variant_id=102, location_id=3, quantity=1, unit_price=620_000_000)],
        payments=[dict(id=1, type="deposit", amount=294_500_000, status="paid", method="Chuyển khoản", paid_at=now)]))
    db.inventory.create_index("location_id")
    db.orders.create_index([("customer_id", 1), ("order_date", 1)])
    db.edition_units.create_index([("variant_id", 1), ("status", 1)])


def place_order(db, s, customer_id, items, address, reserve="version"):
    """Giao dịch Đặt hàng như order.service.ts. s = ClientSession (trong transaction) hoặc None.

    reserve = "version": đọc version rồi updateOne có điều kiện version (như app)
    reserve = "cond":    updateOne có điều kiện còn hàng, $inc nguyên tử
    """
    cust = db.customers.find_one({"_id": customer_id}, session=s)
    tier = db.membership_tiers.find_one({"_id": cust["tier_id"]}, session=s)
    its = sorted(items, key=lambda i: i["variant_id"])
    vmap = {v["_id"]: v for v in db.variants.find({"_id": {"$in": [i["variant_id"] for i in its]},
                                                     "status": "active"}, session=s)}
    subtotal = sum(vmap[i["variant_id"]]["price"] * i["quantity"] for i in its)
    discount = round(subtotal * tier["discount_pct"] / 100)
    total = max(0, subtotal - discount)
    oid = ObjectId()
    lines = []
    for n, it in enumerate(its, 1):
        v = vmap[it["variant_id"]]
        serial = None
        if v["product"]["is_limited"]:
            u = db.edition_units.find_one_and_update(
                {"variant_id": v["_id"], "status": "available"}, {"$set": {"status": "reserved", "order_id": oid}},
                sort=[("_id", 1)], return_document=ReturnDocument.AFTER, session=s)
            if not u:
                raise AppError("EDITION_SOLD_OUT")
            serial = u["serial_no"]
        key = inv_id(v["_id"], it["location_id"])
        avail = {"$expr": {"$gte": [{"$subtract": ["$qty_on_hand", "$qty_reserved"]}, it["quantity"]]}}
        if reserve == "version":
            inv = db.inventory.find_one({"_id": key}, session=s)
            if not inv or inv["qty_on_hand"] - inv["qty_reserved"] < it["quantity"]:
                raise AppError("OUT_OF_STOCK")
            r = db.inventory.update_one({"_id": key, "version": inv["version"], **avail},
                                        {"$inc": {"qty_reserved": it["quantity"], "version": 1}}, session=s)
            if r.matched_count == 0:
                raise AppError("VERSION_CONFLICT")
        else:
            r = db.inventory.update_one({"_id": key, **avail},
                                        {"$inc": {"qty_reserved": it["quantity"], "version": 1}}, session=s)
            if r.matched_count == 0:
                raise AppError("OUT_OF_STOCK")
        lines.append(dict(line=n, variant_id=v["_id"], location_id=it["location_id"], quantity=it["quantity"],
                          unit_price=v["price"], serial_no=serial))
    deposit = round(total * 0.5)
    today = datetime.datetime.now()
    db.orders.insert_one(dict(
        _id=oid, customer_id=customer_id, sales_user_id=None, order_date=today, status="pending",
        subtotal=subtotal, discount=discount, total=total, shipping_address=address, items=lines,
        payments=[dict(id=1, type="deposit", amount=deposit, due_date=today, status="pending"),
                  dict(id=2, type="final", amount=total - deposit, due_date=today + datetime.timedelta(days=30),
                       status="pending")]), session=s)
    return oid


def deliver_order(db, s, order_id, sales_user_id):
    """Giao dịch Bàn giao (đơn -> delivered) như sales.service.ts: 4 bước."""
    o = db.orders.find_one({"_id": order_id}, session=s)
    db.orders.update_one({"_id": order_id, "sales_user_id": sales_user_id}, {"$set": {"status": "delivered"}}, session=s)
    for it in o["items"]:
        db.inventory.update_one({"_id": inv_id(it["variant_id"], it["location_id"])},
                                {"$inc": {"qty_on_hand": -it["quantity"], "qty_reserved": -it["quantity"],
                                          "version": 1}}, session=s)
    db.edition_units.update_many({"order_id": order_id}, {"$set": {"status": "sold"}}, session=s)
    db.customers.update_one({"_id": o["customer_id"]}, {"$inc": {"total_spent": o["total"]}}, session=s)
