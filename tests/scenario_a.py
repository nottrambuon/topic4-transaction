"""Kịch bản A: Atomicity và xử lý lỗi (1 phiên)."""
from lib import app_mysql as AM
from lib import mongo_kit as mg
from lib import mongo_model as M
from lib import mysql_kit as my
from lib.framework import case

M_ORDERS = "SELECT (SELECT COUNT(*) FROM orders) o, (SELECT COUNT(*) FROM order_items) i, (SELECT COUNT(*) FROM payments) p"


def my_counts():
    r = my.q(M_ORDERS)[0]
    return [r["o"], r["i"], r["p"]]


def my_reserved(v, loc):
    return my.q("SELECT qty_reserved FROM inventory WHERE variant_id = %s AND location_id = %s", (v, loc))[0]["qty_reserved"]


def mg_reserved(v, loc):
    return mg.db.inventory.find_one({"_id": M.inv_id(v, loc)})["qty_reserved"]


# --------------------------------------------------------------------------------------------- A1
@case("A1", "MySQL", "Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: hủy trọn giao dịch ghi nhiều bảng",
      "ROLLBACK hủy mọi thay đổi của transaction (orders, order_items, inventory); AUTO_INCREMENT không được trả lại.")
def a1_my(ctx):
    my.reset()
    A = my.Sess(ctx, "A")
    ctx.step("Phần 1: các câu lệnh của giao dịch Đặt hàng, lệnh giữ chỗ vi phạm CHECK của schema app")
    A.x("START TRANSACTION")
    A.x("INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address) "
        "VALUES (2, 580000000, 0, 580000000, '5 Tràng Tiền')")
    A.x("SET @oid = LAST_INSERT_ID()")
    A.x("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) "
        "VALUES (@oid, 401, 1, 2, 290000000)")
    r = A.x("UPDATE inventory SET qty_reserved = qty_reserved + 2, version = version + 1 "
            "WHERE variant_id = 401 AND location_id = 1")
    ctx.check("Mã lỗi khi giữ chỗ vượt tồn", r.code, 3819, why="CHECK chk_inventory_reserved_le_on_hand")
    A.x("ROLLBACK")
    ctx.check("Số đơn / dòng hàng / phiếu thanh toán sau ROLLBACK", my_counts(), [1, 1, 1],
              why="chỉ còn đơn #1 có sẵn trong dữ liệu mẫu")
    ctx.check("Giữ chỗ 401 @ Showroom Q1", my_reserved(401, 1), 0)
    ctx.note("Đơn kế tiếp thành công nhận id mấy?")
    A.x("START TRANSACTION")
    A.x("INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address) "
        "VALUES (2, 290000000, 0, 290000000, '5 Tràng Tiền')")
    r = A.x("SELECT LAST_INSERT_ID() AS id")
    A.x("COMMIT")
    ctx.check("id của đơn kế tiếp", r.first("id"), 3, why="số 2 đã cấp cho giao dịch bị hủy không được trả lại")

    my.reset()
    ctx.step("Phần 2: placeOrder đúng như order.service.ts, đơn 2 dòng: sofa 101 @ Q1 (còn 2) + 2 bàn Venice @ Q1 (còn 1)")
    con = my.connect()
    ctx.log("A", "placeOrder(customer 3, [{101, Q1, 1}, {401, Q1, 2}]) -> withTransaction(REPEATABLE READ)")
    code = None
    try:
        AM.place_order(con, 3, [dict(variant_id=101, location_id=1, quantity=1),
                                dict(variant_id=401, location_id=1, quantity=2)], "88 Võ Văn Tần")
    except AM.AppError as e:
        code = e.code
    ctx.log("A", f"=> lỗi ứng dụng {code}; withTransaction gọi ROLLBACK")
    con.close()
    ctx.check("Lỗi ứng dụng", code, "OUT_OF_STOCK", why="app kiểm tra tồn trước khi UPDATE")
    ctx.check("Giữ chỗ sofa 101 @ Q1 (dòng 1 đã giữ trước khi dòng 2 lỗi)", my_reserved(101, 1), 0,
              why="ROLLBACK hoàn tác cả lượt giữ chỗ hợp lệ")
    ctx.check("Số đơn / dòng hàng / phiếu thanh toán", my_counts(), [1, 1, 1])
    A.close()


@case("A1", "MongoDB", "Đặt 2 bàn Venice khi Showroom Q1 chỉ còn 1: abort hủy trọn giao dịch",
      "Lỗi validator làm abort cả transaction; không dùng transaction thì document đơn hàng đã ghi vẫn còn (đơn ma).")
def a1_mg(ctx):
    mg.reset()
    db = mg.db
    order = dict(customer_id=2, status="pending", subtotal=580_000_000, discount=0, total=580_000_000,
                 shipping_address="5 Tràng Tiền",
                 items=[dict(line=1, variant_id=401, location_id=1, quantity=2, unit_price=290_000_000)],
                 payments=[dict(id=1, type="deposit", amount=290_000_000, status="pending")])
    A = mg.Sess(ctx, "A")
    ctx.step("Phần 1: có transaction")
    A.start()
    A.op("orders.insertOne({ customer_id: 2, items: [{ variant_id: 401, location_id: 1, quantity: 2 }], ... })",
         lambda s: db.orders.insert_one(dict(order), session=s))
    r = A.op("inventory.updateOne({ _id: \"401:1\" }, { $inc: { qty_reserved: 2, version: 1 } })",
             lambda s: db.inventory.update_one({"_id": "401:1"}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    ctx.check("Mã lỗi khi giữ chỗ vượt tồn", r.code, 121, why="validator của collection inventory")
    A.abort()
    ctx.check("Số document orders", db.orders.count_documents({}), 1)
    ctx.check("Giữ chỗ 401 @ Showroom Q1", mg_reserved(401, 1), 0)

    ctx.step("Phần 2: không dùng transaction (hai lệnh ghi độc lập)")
    A.op("orders.insertOne({ ... })", lambda s: db.orders.insert_one(dict(order)))
    r = A.op("inventory.updateOne({ _id: \"401:1\" }, { $inc: { qty_reserved: 2 } })",
             lambda s: db.inventory.update_one({"_id": "401:1"}, {"$inc": {"qty_reserved": 2, "version": 1}}))
    ctx.check("Mã lỗi", r.code, 121)
    ctx.check("Số document orders", db.orders.count_documents({}), 2,
              why="đơn ma: có đơn nhưng không giữ được hàng")

    mg.reset()
    ctx.step("Phần 3: placeOrder như app trong withTransaction, đơn 2 dòng: sofa 101 @ Q1 + 2 bàn Venice @ Q1")
    code = None
    with mg.client.start_session() as s:
        try:
            s.with_transaction(lambda ss: M.place_order(db, ss, 3, [dict(variant_id=101, location_id=1, quantity=1),
                                                                    dict(variant_id=401, location_id=1, quantity=2)],
                                                        "88 Võ Văn Tần"), **mg.TXN)
        except M.AppError as e:
            code = e.code
    ctx.log("A", f"withTransaction(placeOrder(...)) => lỗi ứng dụng {code}; driver abort transaction")
    ctx.check("Lỗi ứng dụng", code, "OUT_OF_STOCK")
    ctx.check("Giữ chỗ sofa 101 @ Q1", mg_reserved(101, 1), 0, why="abort hoàn tác lượt giữ chỗ của dòng 1")
    ctx.check("Số document orders", db.orders.count_documents({}), 1)
    A.end()


# --------------------------------------------------------------------------------------------- A2
@case("A2", "MySQL", "Lỗi giữa giao dịch nhưng ứng dụng vẫn COMMIT",
      "InnoDB chỉ rollback câu lệnh lỗi, transaction vẫn mở: COMMIT lưu phần còn lại (đơn ma). "
      "withTransaction của app và EXIT HANDLER của procedure chặn được.")
def a2_my(ctx):
    my.reset()
    A = my.Sess(ctx, "A")
    stmts = [
        "INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address) "
        "VALUES (2, 580000000, 0, 580000000, '5 Tràng Tiền')",
        "SET @oid = LAST_INSERT_ID()",
        "INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) VALUES (@oid, 401, 1, 2, 290000000)",
        "UPDATE inventory SET qty_reserved = qty_reserved + 2, version = version + 1 WHERE variant_id = 401 AND location_id = 1",
        "INSERT INTO payments (order_id, type, amount, due_date, status) VALUES (@oid, 'deposit', 290000000, CURDATE(), 'pending')",
    ]
    ctx.step("Phần 1: bỏ qua lỗi rồi COMMIT")
    A.x("START TRANSACTION")
    codes = [A.x(s).code for s in stmts]
    ctx.check("Lệnh giữ chỗ lỗi, các lệnh khác chạy tiếp", codes, [None, None, None, 3819, None])
    A.x("COMMIT")
    ctx.check("Số đơn / dòng hàng / phiếu thanh toán được lưu", my_counts(), [2, 2, 2],
              why="đơn ma: có đơn 580 triệu và phiếu cọc nhưng không giữ được chiếc bàn nào")
    ctx.check("Giữ chỗ 401 @ Showroom Q1", my_reserved(401, 1), 0)

    my.reset()
    ctx.step("Phần 2: cùng các câu lệnh, bọc trong withTransaction như config/db.ts (lỗi -> ROLLBACK)")
    con = my.connect()
    err = None
    try:
        AM.with_transaction(con, lambda cur: [cur.execute(s) for s in stmts])
    except Exception as e:  # noqa: BLE001
        err = e.args[0]
    ctx.log("A", f"withTransaction(...) => lỗi {err}, ROLLBACK")
    ctx.check("Số đơn / dòng hàng / phiếu thanh toán", my_counts(), [1, 1, 1])

    ctx.step("Phần 3: stored procedure sp_place_order (EXIT HANDLER: ROLLBACK; RESIGNAL)")
    r = A.x("CALL sp_place_order(2, 401, 1, 2, '5 Tràng Tiền', @oid)")
    ctx.check("Lỗi trả về ứng dụng", r.error.args[1] if r.error else None, "OUT_OF_STOCK")
    ctx.check("Số đơn / dòng hàng / phiếu thanh toán", my_counts(), [1, 1, 1])
    con.close()
    A.close()


@case("A2", "MongoDB", "Lỗi giữa giao dịch nhưng ứng dụng vẫn commit",
      "Lỗi của một thao tác làm server hủy cả transaction; lệnh sau và commit đều báo NoSuchTransaction (251).")
def a2_mg(ctx):
    mg.reset()
    db = mg.db
    A = mg.Sess(ctx, "A")
    A.start()
    A.op("orders.insertOne({ customer_id: 2, total: 580000000, items: [...] })",
         lambda s: db.orders.insert_one(dict(customer_id=2, total=580_000_000, items=[], payments=[]), session=s))
    r1 = A.op("inventory.updateOne({ _id: \"401:1\" }, { $inc: { qty_reserved: 2 } })",
              lambda s: db.inventory.update_one({"_id": "401:1"}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    r2 = A.op("orders.updateOne({ customer_id: 2 }, { $push: { payments: { type: \"deposit\", amount: 290000000 } } })",
              lambda s: db.orders.update_one({"customer_id": 2}, {"$push": {"payments": {"type": "deposit"}}}, session=s))
    r3 = A.commit()
    ctx.check("Mã lỗi: giữ chỗ / lệnh tiếp theo / commit", [r1.code, r2.code, r3.code], [121, 251, 251])
    ctx.check("Số document orders", db.orders.count_documents({}), 1, why="không có đơn ma")
    A.end()


# --------------------------------------------------------------------------------------------- A3
@case("A3", "MySQL", "Đổi kho xuất cho riêng một dòng hàng bằng SAVEPOINT",
      "ROLLBACK TO SAVEPOINT hủy riêng phần sau điểm đánh dấu, giữ lượt giữ chỗ sofa hợp lệ.")
def a3_my(ctx):
    my.reset()
    A = my.Sess(ctx, "A")
    A.x("START TRANSACTION")
    A.x("INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address) "
        "VALUES (3, 1060000000, 0, 1060000000, '88 Võ Văn Tần')")
    A.x("SET @oid = LAST_INSERT_ID()")
    A.x("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) VALUES (@oid, 101, 1, 1, 480000000)")
    A.x("UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 WHERE variant_id = 101 AND location_id = 1")
    A.x("SAVEPOINT sp_line2")
    A.x("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) VALUES (@oid, 401, 1, 2, 290000000)")
    r = A.x("UPDATE inventory SET qty_reserved = qty_reserved + 2, version = version + 1 WHERE variant_id = 401 AND location_id = 1")
    ctx.check("Giữ 2 bàn Venice tại Q1", r.code, 3819)
    A.x("ROLLBACK TO SAVEPOINT sp_line2")
    A.x("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) VALUES (@oid, 401, 3, 2, 290000000)")
    A.x("UPDATE inventory SET qty_reserved = qty_reserved + 2, version = version + 1 WHERE variant_id = 401 AND location_id = 3")
    A.x("COMMIT")
    items = [[r["variant_id"], r["location_id"], r["quantity"]] for r in
             my.q("SELECT variant_id, location_id, quantity FROM order_items WHERE order_id = 2 ORDER BY id")]
    ctx.check("Dòng hàng của đơn mới [biến thể, địa điểm, số lượng]", items, [[101, 1, 1], [401, 3, 2]])
    ctx.check("Giữ chỗ 101@Q1 / 401@Q1 / 401@Kho BD",
              [my_reserved(101, 1), my_reserved(401, 1), my_reserved(401, 3)], [1, 0, 2])
    A.close()


@case("A3", "MongoDB", "Đổi kho xuất cho một dòng hàng khi không có SAVEPOINT",
      "Không có savepoint: lỗi hủy cả transaction, kể cả lượt giữ sofa hợp lệ. Cập nhật có điều kiện (matched 0, "
      "không phát sinh lỗi) cho phép thử kho khác trong cùng transaction.")
def a3_mg(ctx):
    mg.reset()
    db = mg.db
    A = mg.Sess(ctx, "A")
    ctx.step("Phần 1: để validator báo lỗi")
    A.start()
    A.op("inventory.updateOne({ _id: \"101:1\" }, { $inc: { qty_reserved: 1 } })",
         lambda s: db.inventory.update_one({"_id": "101:1"}, {"$inc": {"qty_reserved": 1, "version": 1}}, session=s))
    r = A.op("inventory.updateOne({ _id: \"401:1\" }, { $inc: { qty_reserved: 2 } })",
             lambda s: db.inventory.update_one({"_id": "401:1"}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    r2 = A.op("inventory.updateOne({ _id: \"401:3\" }, { $inc: { qty_reserved: 2 } })   -- thử kho khác",
              lambda s: db.inventory.update_one({"_id": "401:3"}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    ctx.check("Mã lỗi: giữ 401@Q1 / thử 401@Kho BD", [r.code, r2.code], [121, 251])
    A.abort()
    ctx.check("Giữ chỗ sofa 101@Q1 sau khi transaction bị hủy", mg_reserved(101, 1), 0,
              why="mất cả lượt giữ hợp lệ, phải chạy lại từ đầu")

    ctx.step("Phần 2: cập nhật có điều kiện còn hàng (không phát sinh lỗi) rồi thử kho khác")
    cond = {"$expr": {"$gte": [{"$subtract": ["$qty_on_hand", "$qty_reserved"]}, 2]}}
    A.start()
    A.op("inventory.updateOne({ _id: \"101:1\", còn hàng >= 1 }, { $inc: { qty_reserved: 1 } })",
         lambda s: db.inventory.update_one({"_id": "101:1"}, {"$inc": {"qty_reserved": 1, "version": 1}}, session=s))
    a = A.op("inventory.updateOne({ _id: \"401:1\", còn hàng >= 2 }, { $inc: { qty_reserved: 2 } })",
             lambda s: db.inventory.update_one({"_id": "401:1", **cond}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    b = A.op("inventory.updateOne({ _id: \"401:3\", còn hàng >= 2 }, { $inc: { qty_reserved: 2 } })",
             lambda s: db.inventory.update_one({"_id": "401:3", **cond}, {"$inc": {"qty_reserved": 2, "version": 1}}, session=s))
    A.op("orders.insertOne({ customer_id: 3, items: [{101, Q1, 1}, {401, Kho BD, 2}], ... })",
         lambda s: db.orders.insert_one(dict(_id=2, customer_id=3, total=1_060_000_000, items=[
             dict(variant_id=101, location_id=1, quantity=1), dict(variant_id=401, location_id=3, quantity=2)],
             payments=[]), session=s))
    A.commit()
    ctx.check("matched ở Q1 / ở Kho BD", [a.value.matched_count, b.value.matched_count], [0, 1])
    o = db.orders.find_one({"_id": 2})
    ctx.check("Dòng hàng của đơn mới", [[i["variant_id"], i["location_id"], i["quantity"]] for i in o["items"]],
              [[101, 1, 1], [401, 3, 2]])
    ctx.check("Giữ chỗ 101@Q1 / 401@Q1 / 401@Kho BD", [mg_reserved(101, 1), mg_reserved(401, 1), mg_reserved(401, 3)],
              [1, 0, 2])
    A.end()


# --------------------------------------------------------------------------------------------- A4
@case("A4", "MySQL", "Tạo bảng giữa giao dịch tăng giá 10% rồi ROLLBACK",
      "CREATE TABLE gây implicit commit: lệnh tăng giá trước đó đã được commit, ROLLBACK không còn tác dụng.")
def a4_my(ctx):
    my.reset()
    A = my.Sess(ctx, "A")
    A.x("START TRANSACTION")
    A.x("UPDATE product_variants SET price = price * 1.10 WHERE id IN (101, 102)")
    A.x("CREATE TABLE price_audit (id INT PRIMARY KEY, note VARCHAR(100))")
    A.x("ROLLBACK")
    p = [int(r["price"]) for r in my.q("SELECT price FROM product_variants WHERE id IN (101, 102) ORDER BY id")]
    ctx.check("Giá 101 / 102 sau ROLLBACK", p, [528000000, 682000000], why="giá mới đã bị commit ngầm")
    t = my.q("SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema = 'luxury_furniture' "
             "AND table_name = 'price_audit'")[0]["n"]
    ctx.check("Bảng price_audit tồn tại", t, 1)
    A.close()


@case("A4", "MongoDB", "Tạo index / collection giữa giao dịch tăng giá 10%",
      "createIndex trên collection đã có dữ liệu bị từ chối trong transaction và làm transaction bị hủy; "
      "collection tạo mới trong transaction được rollback khi abort.")
def a4_mg(ctx):
    mg.reset()
    db = mg.db
    A = mg.Sess(ctx, "A")
    ctx.step("Phần 1: createIndex trên collection variants (đã có dữ liệu); DDL trong transaction cần readConcern local")
    A.start(read_concern=mg.ReadConcern("local"))
    A.op("variants.updateMany({ _id: { $in: [101, 102] } }, giá x 1,1)",
         lambda s: [db.variants.update_one({"_id": 101}, {"$set": {"price": 528_000_000}}, session=s),
                    db.variants.update_one({"_id": 102}, {"$set": {"price": 682_000_000}}, session=s)][1])
    r = A.op("variants.createIndex({ sku: 1 })", lambda s: db.variants.create_index("sku", session=s))
    c = A.commit()
    ctx.check("Mã lỗi createIndex / commit", [r.code, c.code], [263, 251])
    ctx.check("Giá 101 / 102", [db.variants.find_one({"_id": v})["price"] for v in (101, 102)],
              [480_000_000, 620_000_000], why="cả giao dịch tăng giá bị hủy")

    ctx.step("Phần 2: tạo collection mới trong transaction (readConcern local) rồi abort")
    A.start(read_concern=mg.ReadConcern("local"))
    A.op("db.createCollection(\"price_audit\")", lambda s: db.create_collection("price_audit", session=s).name)
    A.op("price_audit.insertOne({ note: \"tăng giá 10%\" })",
         lambda s: db.price_audit.insert_one({"note": "tăng giá 10%"}, session=s))
    A.abort()
    ctx.check("Collection price_audit tồn tại sau abort", "price_audit" in db.list_collection_names(), False)
    A.end()
