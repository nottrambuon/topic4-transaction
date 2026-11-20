"""Kịch bản B: Isolation và tranh chấp (2 phiên A/B xen kẽ, thứ tự lệnh cố định)."""
import time

from lib import mongo_kit as mg
from lib import mysql_kit as my
from lib.framework import case

INV = "SELECT qty_on_hand - qty_reserved AS con_ban FROM inventory WHERE variant_id = 401 AND location_id = 1"


def reserved(v, loc):
    return my.q("SELECT qty_reserved FROM inventory WHERE variant_id = %s AND location_id = %s", (v, loc))[0]["qty_reserved"]


def mg_reserved(v, loc):
    return mg.db.inventory.find_one({"_id": f"{v}:{loc}"})["qty_reserved"]


# --------------------------------------------------------------------------------------------- B1
@case("B1", "MySQL", "Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read)",
      "READ UNCOMMITTED đọc được giữ chỗ chưa commit (0 rồi 1); READ COMMITTED không (1 và 1).")
def b1_my(ctx):
    seen = {}
    for iso in ("READ UNCOMMITTED", "READ COMMITTED"):
        my.reset()
        ctx.step(f"Phiên B ở mức {iso}")
        A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B", isolation=iso)
        A.x("START TRANSACTION")
        A.x("UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 WHERE variant_id = 401 AND location_id = 1")
        r1 = B.x(INV).first("con_ban")
        A.x("ROLLBACK")
        r2 = B.x(INV).first("con_ban")
        seen[iso] = [r1, r2]
        A.close(), B.close()
    ctx.check("READ UNCOMMITTED: số bàn còn bán [trước, sau khi A hủy]", seen["READ UNCOMMITTED"], [0, 1],
              why="dirty read: thấy chiếc bàn đã hết dù giao dịch của A chưa commit")
    ctx.check("READ COMMITTED: số bàn còn bán [trước, sau khi A hủy]", seen["READ COMMITTED"], [1, 1])


@case("B1", "MongoDB", "Tra cứu bàn Venice còn bán khi phiên kia đang giữ chỗ rồi hủy (dirty read)",
      "MongoDB không cho đọc thay đổi chưa commit, cả trong lẫn ngoài transaction.")
def b1_mg(ctx):
    mg.reset()
    db = mg.db
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")

    def avail(s=None):
        d = db.inventory.find_one({"_id": "401:1"}, session=s)
        return d["qty_on_hand"] - d["qty_reserved"]
    A.start()
    A.op("inventory.updateOne({ _id: \"401:1\" }, { $inc: { qty_reserved: 1 } })",
         lambda s: db.inventory.update_one({"_id": "401:1"}, {"$inc": {"qty_reserved": 1, "version": 1}}, session=s))
    r1 = B.op("inventory.findOne({ _id: \"401:1\" }) -> còn bán (ngoài transaction)", lambda s: avail()).value
    B.start()
    r2 = B.op("inventory.findOne({ _id: \"401:1\" }) -> còn bán (trong transaction)", lambda s: avail(s)).value
    B.commit()
    A.abort()
    ctx.check("Số bàn còn bán [ngoài transaction, trong transaction]", [r1, r2], [1, 1])
    A.end(), B.end()


# --------------------------------------------------------------------------------------------- B2
Q_PRICE = "SELECT price FROM product_variants WHERE id = 101"
Q_STOCK = "SELECT COUNT(*) AS so_ma, SUM(qty_on_hand) AS tong_ton FROM inventory WHERE location_id = 3"


def b2_writer(B):
    B.x("UPDATE product_variants SET price = 520000000 WHERE id = 101")
    B.x("INSERT INTO inventory (variant_id, location_id, qty_on_hand, qty_reserved) VALUES (301, 3, 1, 0)")


@case("B2", "MySQL", "Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho (non-repeatable read, phantom)",
      "READ COMMITTED thấy giá mới và dòng mới giữa hai lần đọc; REPEATABLE READ không thấy; locking read (FOR SHARE) "
      "ở REPEATABLE READ luôn đọc bản mới nhất.")
def b2_my(ctx):
    out = {}
    for iso, locking in (("READ COMMITTED", False), ("REPEATABLE READ", False), ("REPEATABLE READ", True)):
        my.reset()
        label = iso + (" + FOR SHARE" if locking else "")
        ctx.step(f"Phiên báo cáo A ở mức {label}")
        A, B = my.Sess(ctx, "A", isolation=iso), my.Sess(ctx, "B")
        A.x("START TRANSACTION")
        p1, s1 = A.x(Q_PRICE).first("price"), A.x(Q_STOCK).first()
        b2_writer(B)
        p2 = A.x(Q_PRICE).first("price")
        s2 = A.x(Q_STOCK + (" FOR SHARE" if locking else "")).first()
        A.x("COMMIT")
        out[label] = [int(p1) // 1_000_000, int(p2) // 1_000_000, [s1["so_ma"], int(s1["tong_ton"])],
                      [s2["so_ma"], int(s2["tong_ton"])]]
        A.close(), B.close()
    ctx.check("READ COMMITTED [giá lần 1, lần 2 (triệu), (số mã, tổng tồn) lần 1, lần 2]", out["READ COMMITTED"],
              [480, 520, [3, 13], [4, 14]], why="non-repeatable read và phantom")
    ctx.check("REPEATABLE READ", out["REPEATABLE READ"], [480, 480, [3, 13], [3, 13]], why="cùng một read view")
    ctx.check("REPEATABLE READ, lần đọc 2 dùng FOR SHARE", out["REPEATABLE READ + FOR SHARE"],
              [480, 480, [3, 13], [4, 14]], why="locking read đọc bản mới nhất đã commit")


@case("B2", "MongoDB", "Báo cáo tồn Kho Bình Dương trong lúc có đổi giá và nhập kho",
      "Transaction snapshot không thấy thay đổi đã commit sau khi nó bắt đầu đọc; sau commit mới thấy.")
def b2_mg(ctx):
    mg.reset()
    db = mg.db
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")

    def price(s=None):
        return db.variants.find_one({"_id": 101}, session=s)["price"] // 1_000_000

    def stock(s=None):
        r = list(db.inventory.aggregate([{"$match": {"location_id": 3}},
                                         {"$group": {"_id": None, "n": {"$sum": 1}, "t": {"$sum": "$qty_on_hand"}}}],
                                        session=s))[0]
        return [r["n"], r["t"]]
    A.start()
    p1 = A.op("variants.findOne({ _id: 101 }).price (triệu)", lambda s: price(s)).value
    s1 = A.op("inventory.aggregate([{ $match: { location_id: 3 } }, { $group: số mã, tổng tồn }])", lambda s: stock(s)).value
    B.op("variants.updateOne({ _id: 101 }, { $set: { price: 520000000 } })",
         lambda s: db.variants.update_one({"_id": 101}, {"$set": {"price": 520_000_000}}))
    B.op("inventory.insertOne({ _id: \"301:3\", qty_on_hand: 1 })",
         lambda s: db.inventory.insert_one(dict(_id="301:3", variant_id=301, location_id=3, qty_on_hand=1,
                                                qty_reserved=0, version=0)))
    p2 = A.op("variants.findOne({ _id: 101 }).price (triệu)", lambda s: price(s)).value
    s2 = A.op("inventory.aggregate(...)", lambda s: stock(s)).value
    A.commit()
    s3 = A.op("inventory.aggregate(...) sau commit", lambda s: stock()).value
    ctx.check("Trong transaction [giá lần 1, lần 2, (số mã, tổng tồn) lần 1, lần 2]", [p1, p2, s1, s2],
              [480, 480, [3, 13], [3, 13]])
    ctx.check("Sau commit (số mã, tổng tồn)", s3, [4, 14])
    A.end(), B.end()


# --------------------------------------------------------------------------------------------- B3
SEL = "SELECT qty_reserved, version FROM inventory WHERE variant_id = 101 AND location_id = 3"


@case("B3", "MySQL", "Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update)",
      "REPEATABLE READ không chặn lost update kiểu đọc rồi ghi (kết quả 1 thay vì 2). FOR UPDATE, cột version của app "
      "và cập nhật có điều kiện đều cho kết quả đúng, nhưng version của app từ chối lượt đến sau.")
def b3_my(ctx):
    my.reset()
    ctx.step("Đối chứng: đọc rồi ghi giá trị tự tính (REPEATABLE READ)")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    a = A.x(SEL).first("qty_reserved")
    b = B.x(SEL).first("qty_reserved")
    A.x("UPDATE inventory SET qty_reserved = %s WHERE variant_id = 101 AND location_id = 3", (a + 1,))
    A.x("COMMIT")
    B.x("UPDATE inventory SET qty_reserved = %s WHERE variant_id = 101 AND location_id = 3", (b + 1,))
    B.x("COMMIT")
    ctx.check("Đối chứng: giữ chỗ cuối cùng", reserved(101, 3), 1, why="lost update: đúng ra phải là 2")
    A.close(), B.close()

    my.reset()
    ctx.step("Cách 1: khóa bi quan SELECT ... FOR UPDATE")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    a = A.x(SEL + " FOR UPDATE").first("qty_reserved")
    h = B.bg(SEL + " FOR UPDATE")
    time.sleep(1.5)
    A.x("UPDATE inventory SET qty_reserved = %s, version = version + 1 WHERE variant_id = 101 AND location_id = 3", (a + 1,))
    A.x("COMMIT")
    rb = h.wait()
    B.x("UPDATE inventory SET qty_reserved = %s, version = version + 1 WHERE variant_id = 101 AND location_id = 3",
        (rb.first("qty_reserved") + 1,))
    B.x("COMMIT")
    ctx.check("Cách 1: thời gian B chờ khóa (s)", round(rb.waited, 2), "≥ 1,4", ok=rb.waited >= 1.4, why="A giữ khóa 1,5 s")
    ctx.check("Cách 1: giữ chỗ cuối cùng", reserved(101, 3), 2)
    A.close(), B.close()

    my.reset()
    ctx.step("Cách 2: optimistic locking bằng cột version, đúng câu lệnh của inventory.repository.ts")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    upd = ("UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 WHERE variant_id = 101 "
           "AND location_id = 3 AND version = %s AND (qty_on_hand - qty_reserved) >= 1")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    va = A.x(SEL).first("version")
    vb = B.x(SEL).first("version")
    A.x(upd, (va,))
    h = B.bg(upd.replace("%s", str(vb)))
    time.sleep(1.0)
    A.x("COMMIT")
    rb = h.wait()
    B.x("ROLLBACK")
    ctx.log("B", "=> app báo VERSION_CONFLICT cho khách (không tự thử lại)")
    after_conflict = reserved(101, 3)
    ctx.note("Thử lại bằng một transaction mới")
    B.x("START TRANSACTION")
    vb = B.x(SEL).first("version")
    B.x(upd, (vb,))
    B.x("COMMIT")
    ctx.check("Cách 2: số dòng B cập nhật được ở lần đầu", rb.affected, 0, why="version đã đổi từ 0 thành 1")
    ctx.check("Cách 2: giữ chỗ sau xung đột / sau khi thử lại", [after_conflict, reserved(101, 3)], [1, 2],
              why="không mất cập nhật, nhưng lượt đến sau bị từ chối nếu không thử lại")
    A.close(), B.close()

    my.reset()
    ctx.step("Cách 3: cập nhật có điều kiện còn hàng, không đọc trước")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    cond = ("UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 "
            "WHERE variant_id = 101 AND location_id = 3 AND (qty_on_hand - qty_reserved) >= 1")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    A.x(cond)
    h = B.bg(cond)
    time.sleep(1.0)
    A.x("COMMIT")
    rb = h.wait()
    B.x("COMMIT")
    ctx.check("Cách 3: B chờ rồi cập nhật được (dòng)", rb.affected, 1)
    ctx.check("Cách 3: giữ chỗ cuối cùng", reserved(101, 3), 2)
    A.close(), B.close()


@case("B3", "MongoDB", "Hai sales cùng giữ chỗ sofa Lawson 240 ở Kho Bình Dương (lost update)",
      "Không dùng transaction: đọc rồi ghi mất cập nhật. Trong transaction, lượt ghi sau bị WriteConflict (112) ngay, "
      "không chờ; thử lại cho kết quả đúng.")
def b3_mg(ctx):
    mg.reset()
    db = mg.db
    key = {"_id": "101:3"}
    ctx.step("Đối chứng: không dùng transaction, đọc rồi ghi giá trị tự tính")
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")
    a = A.op("inventory.findOne({ _id: \"101:3\" }).qty_reserved", lambda s: db.inventory.find_one(key)["qty_reserved"]).value
    b = B.op("inventory.findOne({ _id: \"101:3\" }).qty_reserved", lambda s: db.inventory.find_one(key)["qty_reserved"]).value
    A.op(f"inventory.updateOne({{ _id: \"101:3\" }}, {{ $set: {{ qty_reserved: {a + 1} }} }})",
         lambda s: db.inventory.update_one(key, {"$set": {"qty_reserved": a + 1}}))
    B.op(f"inventory.updateOne({{ _id: \"101:3\" }}, {{ $set: {{ qty_reserved: {b + 1} }} }})",
         lambda s: db.inventory.update_one(key, {"$set": {"qty_reserved": b + 1}}))
    ctx.check("Đối chứng: giữ chỗ cuối cùng", mg_reserved(101, 3), 1, why="lost update: đúng ra phải là 2")

    mg.reset()
    ctx.step("Hai transaction snapshot cùng đọc rồi ghi")
    A.start(), B.start()
    a = A.op("inventory.findOne({ _id: \"101:3\" }).qty_reserved",
             lambda s: db.inventory.find_one(key, session=s)["qty_reserved"]).value
    b = B.op("inventory.findOne({ _id: \"101:3\" }).qty_reserved",
             lambda s: db.inventory.find_one(key, session=s)["qty_reserved"]).value
    A.op(f"inventory.updateOne({{ _id: \"101:3\" }}, {{ $set: {{ qty_reserved: {a + 1} }} }})",
         lambda s: db.inventory.update_one(key, {"$set": {"qty_reserved": a + 1}, "$inc": {"version": 1}}, session=s))
    t = time.perf_counter()
    rb = B.op(f"inventory.updateOne({{ _id: \"101:3\" }}, {{ $set: {{ qty_reserved: {b + 1} }} }})",
              lambda s: db.inventory.update_one(key, {"$set": {"qty_reserved": b + 1}, "$inc": {"version": 1}}, session=s))
    waited = time.perf_counter() - t
    B.abort()
    A.commit()
    ctx.note("withTransaction thấy nhãn TransientTransactionError nên chạy lại cả giao dịch của B")
    B.start()
    b = B.op("inventory.findOne({ _id: \"101:3\" }).qty_reserved",
             lambda s: db.inventory.find_one(key, session=s)["qty_reserved"]).value
    B.op(f"inventory.updateOne({{ _id: \"101:3\" }}, {{ $set: {{ qty_reserved: {b + 1} }} }})",
         lambda s: db.inventory.update_one(key, {"$set": {"qty_reserved": b + 1}, "$inc": {"version": 1}}, session=s))
    B.commit()
    ctx.check("Mã lỗi lượt ghi của B và nhãn", [rb.code, rb.labels()], [112, ["TransientTransactionError"]])
    ctx.check("Thời gian B chờ trước khi nhận lỗi (s)", round(waited, 3), "< 0,1", ok=waited < 0.1,
              why="WiredTiger hủy ngay, không xếp hàng chờ")
    ctx.check("Giữ chỗ cuối cùng sau khi thử lại", mg_reserved(101, 3), 2)
    A.end(), B.end()


# --------------------------------------------------------------------------------------------- B4
Q_PAY = "SELECT type, amount, status FROM payments WHERE order_id = 1"
INS_FINAL = ("INSERT INTO payments (order_id, type, amount, due_date, status) "
             "VALUES (1, 'final', 294500000, CURDATE() + INTERVAL 30 DAY, 'pending')")


def schedule_ok(rows, new_amount=294_500_000, total=589_000_000):
    """Đúng logic createPaymentSchedule của sales.service.ts: tối đa 1 khoản final, tổng không vượt order.total."""
    active = [r for r in rows if r["status"] != "refunded"]
    finals = sum(r["type"] == "final" for r in active)
    s = sum(int(r["amount"]) for r in active)
    return finals + 1 <= 1 and s + new_amount <= total


def pay_state():
    r = my.q("SELECT SUM(type = 'final') AS finals, SUM(amount) AS tong FROM payments WHERE order_id = 1 "
             "AND status <> 'refunded'")[0]
    return [int(r["finals"]), int(r["tong"])]


@case("B4", "MySQL", "Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew)",
      "Ràng buộc 'tổng các khoản ≤ order.total, tối đa 1 khoản final' bị phá ở cách app đang làm (không transaction) và "
      "ở REPEATABLE READ; SERIALIZABLE chặn bằng deadlock; khóa dòng orders bằng FOR UPDATE chặn bằng chờ khóa.")
def b4_my(ctx):
    res = {}
    for mode in ("app (autocommit)", "REPEATABLE READ", "SERIALIZABLE", "REPEATABLE READ + FOR UPDATE orders"):
        my.reset()
        ctx.step(f"Cách: {mode}. Đơn #1 tổng 589 triệu, đã có khoản cọc 294,5 triệu; mỗi yêu cầu thêm khoản final 294,5 triệu")
        iso = "SERIALIZABLE" if mode == "SERIALIZABLE" else None
        A, B = my.Sess(ctx, "A", isolation=iso), my.Sess(ctx, "B", isolation=iso)
        tx = mode != "app (autocommit)"
        if tx:
            A.x("START TRANSACTION"), B.x("START TRANSACTION")
        if mode.endswith("FOR UPDATE orders"):
            A.x("SELECT id FROM orders WHERE id = 1 FOR UPDATE")
            h = B.bg("SELECT id FROM orders WHERE id = 1 FOR UPDATE")
            time.sleep(1.5)
            okA = schedule_ok(A.x(Q_PAY).rows)
            A.x(INS_FINAL) if okA else None
            A.x("COMMIT")
            rb = h.wait()
            okB = schedule_ok(B.x(Q_PAY).rows)
            if okB:
                B.x(INS_FINAL)
            else:
                ctx.log("B", "=> kiểm tra ràng buộc thất bại: từ chối lập lịch")
            B.x("COMMIT")
            res[mode] = dict(state=pay_state(), waited=rb.waited)
            A.close(), B.close()
            continue
        okA = schedule_ok(A.x(Q_PAY).rows)
        okB = schedule_ok(B.x(Q_PAY).rows)
        ctx.note(f"Cả hai đều kiểm tra ràng buộc: A {'đạt' if okA else 'không đạt'}, B {'đạt' if okB else 'không đạt'}")
        if mode == "SERIALIZABLE":
            h = A.bg(INS_FINAL)
            time.sleep(1.0)
            rB = B.x(INS_FINAL)
            rA = h.wait()
            victim, winner = (B, A) if rB.code == 1213 else (A, B)
            codes = sorted([c for c in (rA.code, rB.code) if c])
            winner.x("COMMIT")
            ctx.note(f"Phiên {victim.lane} bị chọn làm nạn nhân deadlock, transaction đã bị rollback; chạy lại")
            victim.x("START TRANSACTION")
            if schedule_ok(victim.x(Q_PAY).rows):
                victim.x(INS_FINAL)
            else:
                ctx.log(victim.lane, "=> kiểm tra ràng buộc thất bại: từ chối lập lịch")
            victim.x("COMMIT")
            res[mode] = dict(state=pay_state(), codes=codes)
        else:
            A.x(INS_FINAL), B.x(INS_FINAL)
            if tx:
                A.x("COMMIT"), B.x("COMMIT")
            res[mode] = dict(state=pay_state())
        A.close(), B.close()
    ctx.check("Như app hiện tại (không transaction): [số khoản final, tổng tiền]", res["app (autocommit)"]["state"],
              [2, 883_500_000], why="write skew: 2 khoản final, vượt order.total 294,5 triệu")
    ctx.check("REPEATABLE READ: [số khoản final, tổng tiền]", res["REPEATABLE READ"]["state"], [2, 883_500_000],
              why="snapshot không thấy dòng của nhau, INSERT không xung đột")
    ctx.check("SERIALIZABLE: mã lỗi của nạn nhân", res["SERIALIZABLE"]["codes"], [1213])
    ctx.check("SERIALIZABLE: [số khoản final, tổng tiền]", res["SERIALIZABLE"]["state"], [1, 589_000_000])
    w = res["REPEATABLE READ + FOR UPDATE orders"]
    ctx.check("FOR UPDATE dòng orders: B chờ (s)", round(w["waited"], 2), "≥ 1,4", ok=w["waited"] >= 1.4)
    ctx.check("FOR UPDATE dòng orders: [số khoản final, tổng tiền]", w["state"], [1, 589_000_000])


@case("B4", "MongoDB", "Hai yêu cầu lập lịch thanh toán cùng lúc cho đơn #1 (write skew)",
      "Snapshot isolation để lọt write skew khi khoản thanh toán là document riêng; khi nhúng payments[] vào document "
      "đơn hàng (mô hình của nhóm), hai giao dịch ghi cùng một document nên WriteConflict chặn được.")
def b4_mg(ctx):
    db = mg.db
    final = dict(type="final", amount=294_500_000, status="pending")

    def ok(pays):
        act = [p for p in pays if p["status"] != "refunded"]
        return sum(p["type"] == "final" for p in act) + 1 <= 1 and sum(p["amount"] for p in act) + 294_500_000 <= 589_000_000

    mg.reset()
    ctx.step("Thiết kế chuẩn hóa: payments là collection riêng (như bảng SQL)")
    db.payments.insert_one(dict(order_id=1, type="deposit", amount=294_500_000, status="paid"))
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")
    A.start(), B.start()
    okA = A.op("payments.find({ order_id: 1 }) -> kiểm tra ràng buộc",
               lambda s: ok(list(db.payments.find({"order_id": 1}, session=s)))).value
    okB = B.op("payments.find({ order_id: 1 }) -> kiểm tra ràng buộc",
               lambda s: ok(list(db.payments.find({"order_id": 1}, session=s)))).value
    A.op("payments.insertOne({ order_id: 1, type: \"final\", amount: 294500000 })",
         lambda s: db.payments.insert_one(dict(order_id=1, **final), session=s))
    B.op("payments.insertOne({ order_id: 1, type: \"final\", amount: 294500000 })",
         lambda s: db.payments.insert_one(dict(order_id=1, **final), session=s))
    A.commit(), B.commit()
    pays = list(db.payments.find({"order_id": 1}))
    sep = [sum(p["type"] == "final" for p in pays), sum(p["amount"] for p in pays)]
    ctx.check("Cả hai qua kiểm tra", [okA, okB], [True, True])
    ctx.check("Collection riêng: [số khoản final, tổng tiền]", sep, [2, 883_500_000], why="write skew")

    mg.reset()
    ctx.step("Thiết kế nhúng: payments[] nằm trong document đơn hàng")
    A.start(), B.start()
    A.op("orders.findOne({ _id: 1 }).payments -> kiểm tra ràng buộc",
         lambda s: ok(db.orders.find_one({"_id": 1}, session=s)["payments"]))
    B.op("orders.findOne({ _id: 1 }).payments -> kiểm tra ràng buộc",
         lambda s: ok(db.orders.find_one({"_id": 1}, session=s)["payments"]))
    A.op("orders.updateOne({ _id: 1 }, { $push: { payments: { type: \"final\", amount: 294500000 } } })",
         lambda s: db.orders.update_one({"_id": 1}, {"$push": {"payments": dict(id=2, **final)}}, session=s))
    rb = B.op("orders.updateOne({ _id: 1 }, { $push: { payments: { type: \"final\", amount: 294500000 } } })",
              lambda s: db.orders.update_one({"_id": 1}, {"$push": {"payments": dict(id=3, **final)}}, session=s))
    B.abort()
    A.commit()
    ctx.note("B chạy lại giao dịch")
    B.start()
    okB2 = B.op("orders.findOne({ _id: 1 }).payments -> kiểm tra ràng buộc",
                lambda s: ok(db.orders.find_one({"_id": 1}, session=s)["payments"])).value
    if not okB2:
        ctx.log("B", "=> kiểm tra ràng buộc thất bại: từ chối lập lịch")
    B.commit()
    pays = db.orders.find_one({"_id": 1})["payments"]
    ctx.check("Nhúng: mã lỗi lượt ghi của B", rb.code, 112)
    ctx.check("Nhúng: [số khoản final, tổng tiền]", [sum(p["type"] == "final" for p in pays), sum(p["amount"] for p in pays)],
              [1, 589_000_000])
    A.end(), B.end()


# --------------------------------------------------------------------------------------------- B5
def upd(v, loc):
    return (f"UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 "
            f"WHERE variant_id = {v} AND location_id = {loc} AND (qty_on_hand - qty_reserved) >= 1")


@case("B5", "MySQL", "Hai đơn giữ hai món theo thứ tự ngược nhau; chờ khóa quá hạn",
      "Deadlock (1213) hủy cả transaction nạn nhân; sắp xếp theo variant_id như app thì không deadlock; "
      "lock wait timeout (1205) chỉ hủy câu lệnh đang chờ, phần đã làm của transaction vẫn còn.")
def b5_my(ctx):
    my.reset()
    ctx.step("Phần 1: A giữ sofa 101 rồi bàn 401; B giữ bàn 401 rồi sofa 101 (Kho Bình Dương)")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    A.x(upd(101, 3))
    B.x(upd(401, 3))
    h = A.bg(upd(401, 3))
    time.sleep(1.0)
    rB = B.x(upd(101, 3))
    rA = h.wait()
    victim, winner = (B, A) if rB.code == 1213 else (A, B)
    winner.x("COMMIT")
    victim.x("COMMIT")
    ctx.check("Mã lỗi của nạn nhân deadlock", sorted(c for c in (rA.code, rB.code) if c), [1213])
    ctx.check("Giữ chỗ 101 / 401 tại Kho BD", [reserved(101, 3), reserved(401, 3)], [1, 1],
              why="chỉ còn 2 lượt giữ của bên thắng; lượt giữ đầu của nạn nhân đã bị rollback cùng transaction")
    A.close(), B.close()

    my.reset()
    ctx.step("Phần 2: cả hai giữ theo thứ tự variant_id tăng dần (như placeOrder của app)")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    A.x("START TRANSACTION"), B.x("START TRANSACTION")
    A.x(upd(101, 3))
    h = B.bg(upd(101, 3))
    A.x(upd(401, 3))
    time.sleep(1.0)
    A.x("COMMIT")
    r1 = h.wait()
    r2 = B.x(upd(401, 3))
    B.x("COMMIT")
    ctx.check("Không có deadlock: mã lỗi của B", [r1.code, r2.code], [None, None])
    ctx.check("Giữ chỗ 101 / 401 tại Kho BD", [reserved(101, 3), reserved(401, 3)], [2, 2])
    A.close(), B.close()

    my.reset()
    ctx.step("Phần 3: lock wait timeout (innodb_lock_wait_timeout = 3 cho phiên B)")
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B", lock_wait_timeout=3)
    A.x("START TRANSACTION")
    A.x(upd(401, 3))
    B.x("START TRANSACTION")
    B.x(upd(101, 3))
    h = B.bg(upd(401, 3))
    rb = h.wait()
    still = B.x("SELECT qty_reserved FROM inventory WHERE variant_id = 101 AND location_id = 3").first("qty_reserved")
    B.x("COMMIT")
    A.x("COMMIT")
    ctx.check("Mã lỗi và thời gian chờ (s)", [rb.code, round(rb.waited, 1)], "[1205, ≈3]",
              ok=rb.code == 1205 and 2.8 <= rb.waited <= 4.0)
    ctx.check("Giữ chỗ sofa của B vẫn còn sau lỗi / sau COMMIT", [still, reserved(101, 3)], [1, 1],
              why="chỉ câu lệnh chờ bị hủy: đơn của B được commit dở dang nếu ứng dụng không ROLLBACK")
    A.close(), B.close()


@case("B5", "MongoDB", "Hai đơn giữ hai món theo thứ tự ngược nhau; giới hạn thời gian của transaction",
      "Không có chờ khóa giữa hai transaction: bên ghi sau bị WriteConflict ngay. Lệnh ghi ngoài transaction thì chờ "
      "transaction kia kết thúc. Transaction quá transactionLifetimeLimitSeconds bị server hủy.")
def b5_mg(ctx):
    mg.reset()
    db = mg.db
    inc = {"$inc": {"qty_reserved": 1, "version": 1}}
    ctx.step("Phần 1: A giữ 101 rồi 401; B giữ 401 rồi 101 (Kho Bình Dương)")
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")
    A.start(), B.start()
    A.op("inventory.updateOne({ _id: \"101:3\" }, $inc)", lambda s: db.inventory.update_one({"_id": "101:3"}, inc, session=s))
    B.op("inventory.updateOne({ _id: \"401:3\" }, $inc)", lambda s: db.inventory.update_one({"_id": "401:3"}, inc, session=s))
    t = time.perf_counter()
    ra = A.op("inventory.updateOne({ _id: \"401:3\" }, $inc)", lambda s: db.inventory.update_one({"_id": "401:3"}, inc, session=s))
    wa = time.perf_counter() - t
    A.abort()
    B.op("inventory.updateOne({ _id: \"101:3\" }, $inc)", lambda s: db.inventory.update_one({"_id": "101:3"}, inc, session=s))
    B.commit()
    ctx.check("Mã lỗi của A và thời gian chờ (s)", [ra.code, round(wa, 3)], "[112, < 0,1]", ok=ra.code == 112 and wa < 0.1)
    ctx.check("Giữ chỗ 101 / 401 tại Kho BD", [mg_reserved(101, 3), mg_reserved(401, 3)], [1, 1])

    mg.reset()
    ctx.step("Phần 2: lệnh ghi ngoài transaction gặp document đang bị transaction giữ")
    A.start()
    A.op("inventory.updateOne({ _id: \"401:3\" }, $inc)", lambda s: db.inventory.update_one({"_id": "401:3"}, inc, session=s))
    h = B.bg("inventory.updateOne({ _id: \"401:3\" }, $inc)   -- ngoài transaction",
             lambda s: db.inventory.update_one({"_id": "401:3"}, inc))
    time.sleep(1.5)
    A.commit()
    rb = h.wait()
    ctx.check("Lệnh ngoài transaction: chờ (s)", round(rb.waited, 2), "≥ 1,4", ok=rb.ok and rb.waited >= 1.4)
    ctx.check("Giữ chỗ 401 tại Kho BD", mg_reserved(401, 3), 2)

    mg.reset()
    ctx.step("Phần 3: đặt tạm transactionLifetimeLimitSeconds = 5 rồi để transaction mở 12 giây")
    nodes = [mg.MongoClient(f"mongodb://127.0.0.1:{p}/?directConnection=true") for p in (27017, 27018, 27019)]
    for n in nodes:
        n.admin.command({"setParameter": 1, "transactionLifetimeLimitSeconds": 5})
    try:
        A.start()
        A.op("inventory.updateOne({ _id: \"101:3\" }, $inc)",
             lambda s: db.inventory.update_one({"_id": "101:3"}, inc, session=s))
        ctx.log("A", "(khách chưa xác nhận, transaction để mở 12 giây)")
        time.sleep(12)
        rc = A.commit()
    finally:
        for n in nodes:
            n.admin.command({"setParameter": 1, "transactionLifetimeLimitSeconds": 60})
            n.close()
    ctx.check("Mã lỗi khi commit", rc.code, 251, why="server đã hủy transaction quá hạn")
    ctx.check("Giữ chỗ 101 tại Kho BD", mg_reserved(101, 3), 0)
    A.end(), B.end()
