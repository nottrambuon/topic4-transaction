"""Kịch bản C: Durability (sập server) và hiệu năng (C2 tuần tự, C3 tranh chấp cao)."""
import csv
import os
import statistics as st
import subprocess
import threading
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from lib import app_mysql as AM
from lib import config as C
from lib import mongo_kit as mg
from lib import mongo_model as M
from lib import mysql_kit as my
from lib.framework import case

RECOVERY_KEYS_MY = ("redo", "Rolling back", "rolled back", "XA crash recovery", "crash recovery", "Rollback of trx",
                    "Database was not shutdown normally", "Starting crash recovery", "Apply batch", "Applying a batch",
                    "ready for connections")
RECOVERY_KEYS_MG = ("Recovering data from the last clean checkpoint", "recovery log replay", "rollback to stable",
                    "Recovery", "recovery", "Unclean shutdown detected", "transitioned to", "Starting replication")


# ============================================================================================== C1
def my_wait_up(timeout=120):
    t = time.perf_counter()
    while time.perf_counter() - t < timeout:
        try:
            my.q("SELECT 1", db=False)
            return time.perf_counter() - t
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    raise RuntimeError("MySQL không khởi động lại được")


@case("C1", "MySQL", "Kill -9 mysqld khi giao dịch Bàn giao đã commit và một đơn khác còn dở dang",
      "Khởi động lại: redo log khôi phục giao dịch đã commit, undo hủy giao dịch chưa commit.", destructive=True)
def c1_my(ctx):
    my.reset()
    A, B = my.Sess(ctx, "A"), my.Sess(ctx, "B")
    ctx.step("A: giao dịch Bàn giao đơn #1 của An (4 bước như sales.service.ts), COMMIT")
    A.x("START TRANSACTION")
    A.x("UPDATE orders SET status = 'delivered' WHERE id = 1 AND sales_user_id = 2")
    A.x("UPDATE inventory SET qty_on_hand = GREATEST(0, qty_on_hand - 1), qty_reserved = GREATEST(0, qty_reserved - 1), "
        "version = version + 1 WHERE variant_id = 102 AND location_id = 3")
    A.x("UPDATE edition_units eu JOIN order_items oi ON eu.order_item_id = oi.id SET eu.status = 'sold' WHERE oi.order_id = 1")
    A.x("UPDATE customers SET total_spent = total_spent + 589000000 WHERE id = 1")
    A.x("COMMIT")
    ctx.step("B: đơn bàn Venice của Chi, chưa COMMIT")
    B.x("START TRANSACTION")
    B.x("UPDATE inventory SET qty_reserved = qty_reserved + 1, version = version + 1 "
        "WHERE variant_id = 401 AND location_id = 1 AND (qty_on_hand - qty_reserved) >= 1")
    B.x("INSERT INTO orders (customer_id, subtotal, discount, total, shipping_address) "
        "VALUES (3, 290000000, 0, 290000000, '88 Võ Văn Tần')")
    B.x("INSERT INTO order_items (order_id, variant_id, location_id, quantity, unit_price) "
        "VALUES (LAST_INSERT_ID(), 401, 1, 1, 290000000)")
    pos = os.path.getsize(C.MYSQL_ERROR_LOG) if os.path.exists(C.MYSQL_ERROR_LOG) else 0
    ctx.step("Sự cố")
    ctx.log("-", f"$ {C.MYSQL_KILL_CMD}")
    subprocess.run(C.MYSQL_KILL_CMD, shell=True, check=False)
    time.sleep(1.0)
    A.close(), B.close()
    ctx.log("-", "$ khởi động lại mysqld")
    t = time.perf_counter()
    subprocess.run(C.MYSQL_START_CMD, shell=True, check=False)
    up = my_wait_up()
    up = time.perf_counter() - t
    ctx.log("-", f"=> mysqld nhận kết nối sau {up:.1f}s")
    time.sleep(1.0)
    with open(C.MYSQL_ERROR_LOG, encoding="utf-8", errors="replace") as f:
        f.seek(pos)
        lines = [ln.rstrip() for ln in f if any(k in ln for k in RECOVERY_KEYS_MY)]
    ctx.note("Nhật ký khôi phục (trích error log):")
    for ln in lines[:20]:
        ctx.log("-", ln[:220])
    ctx.metric("recovery_log", lines)
    ctx.metric("restart_seconds", round(up, 1))
    o = my.q("SELECT status FROM orders WHERE id = 1")[0]["status"]
    inv = my.q("SELECT qty_on_hand, qty_reserved FROM inventory WHERE variant_id = 102 AND location_id = 3")[0]
    spent = int(my.q("SELECT total_spent FROM customers WHERE id = 1")[0]["total_spent"])
    ctx.check("Bàn giao đã commit: [trạng thái đơn, tồn / giữ chỗ 102@Kho BD, total_spent của An]",
              [o, [inv["qty_on_hand"], inv["qty_reserved"]], spent], ["delivered", [2, 0], 1_009_000_000])
    chi = my.q("SELECT COUNT(*) n FROM orders WHERE customer_id = 3")[0]["n"]
    ctx.check("Đơn dở dang của Chi: [số đơn, giữ chỗ 401@Q1]",
              [chi, my.q("SELECT qty_reserved r FROM inventory WHERE variant_id = 401 AND location_id = 1")[0]["r"]],
              [0, 0])
    ctx.check("Log có pha redo (áp dụng redo log)", any("redo" in ln.lower() for ln in lines), True)
    ctx.check("Log có pha undo / rollback giao dịch chưa commit",
              any(("rolling back" in ln.lower()) or ("rolled back" in ln.lower()) or ("rollback" in ln.lower())
                  for ln in lines), True)


def mongo_recovery_lines(f):
    import json
    out = []
    for ln in f:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        m, a = d.get("msg", ""), d.get("attr", {})
        if m == "WiredTiger message":
            msg = a.get("message", {})
            msg = msg.get("msg", "") if isinstance(msg, dict) else str(msg)
            if any(k in msg for k in ("recovery", "Recovering", "rollback to stable")) and msg not in out:
                out.append(msg)
        elif m in ("Recovering data from the last clean checkpoint.", "Completed oplog application for recovery"):
            out.append(m + (f" (numOpsApplied={a['numOpsApplied']})" if "numOpsApplied" in a else ""))
    return out


def primary_port(cl):
    h = cl.admin.command("hello")
    return int(h["primary"].split(":")[1]) if h.get("primary") else None


@case("C1", "MongoDB", "Kill -9 PRIMARY khi giao dịch Bàn giao đã commit (w: majority) và một đơn khác còn dở dang",
      "Replica set bầu PRIMARY mới; giao dịch đã commit với w: majority còn nguyên; giao dịch dở dang bị hủy; "
      "node bị kill tự khôi phục từ checkpoint và journal khi khởi động lại.", destructive=True)
def c1_mg(ctx):
    mg.reset()
    db = mg.db
    A, B = mg.Sess(ctx, "A"), mg.Sess(ctx, "B")
    ctx.step("A: giao dịch Bàn giao đơn #1, commit với w: majority")
    A.start()
    A.op("deliverOrder(1): orders, inventory, edition_units, customers", lambda s: M.deliver_order(db, s, 1, 2) or "ok")
    A.commit()
    ctx.step("B: đơn bàn Venice của Chi, chưa commit")
    B.start()
    B.op("placeOrder(customer 3, [{401, Q1, 1}])",
         lambda s: M.place_order(db, s, 3, [dict(variant_id=401, location_id=1, quantity=1)], "88 Võ Văn Tần"))
    port = primary_port(mg.client)
    idx = port - C.MONGO_BASE_PORT
    logp = os.path.join(C.MONGO_DATA, f"rs{idx}.log")
    pos = os.path.getsize(logp)
    ctx.step("Sự cố")
    ctx.log("-", f"$ kill -9 <mongod PRIMARY cổng {port}>")
    subprocess.run(f"kill -9 $(pgrep -f 'mongod .*--port {port}')", shell=True, check=False)
    t = time.perf_counter()
    probe = MongoClient(C.MONGO_URI, serverSelectionTimeoutMS=2000, w="majority")
    while True:
        try:
            probe[C.DB].failover_probe.insert_one({"t": time.time()})
            break
        except PyMongoError:
            if time.perf_counter() - t > 60:
                raise
            time.sleep(0.1)
    fo = time.perf_counter() - t
    newp = primary_port(probe)
    ctx.log("-", f"=> PRIMARY mới là cổng {newp}, ghi được sau {fo:.1f}s")
    rb = B.commit()
    ctx.metric("failover_seconds", round(fo, 1))
    o = db.orders.find_one({"_id": 1})["status"]
    inv = db.inventory.find_one({"_id": "102:3"})
    spent = db.customers.find_one({"_id": 1})["total_spent"]
    ctx.check("Bàn giao đã commit: [trạng thái đơn, tồn / giữ chỗ 102@Kho BD, total_spent của An]",
              [o, [inv["qty_on_hand"], inv["qty_reserved"]], spent], ["delivered", [2, 0], 1_009_000_000])
    ctx.check("Commit của B sau failover thất bại", not rb.ok, True)
    ctx.check("Đơn dở dang của Chi: [số đơn, giữ chỗ 401@Q1]",
              [db.orders.count_documents({"customer_id": 3}), db.inventory.find_one({"_id": "401:1"})["qty_reserved"]],
              [0, 0])
    ctx.check("Thời gian đến khi ghi được trên PRIMARY mới (s)", round(fo, 1), "≤ 20", ok=fo <= 20)
    ctx.step("Khởi động lại node bị kill")
    subprocess.run([C.MONGOD_BIN, "--replSet", "rs0", "--port", str(port), "--dbpath",
                    os.path.join(C.MONGO_DATA, f"rs{idx}"), "--bind_ip", C.MONGO_BIND_IP, "--fork", "--logpath", logp,
                    "--logappend"], capture_output=True, check=False)
    node = MongoClient(f"mongodb://127.0.0.1:{port}/?directConnection=true", serverSelectionTimeoutMS=30000)
    t = time.perf_counter()
    state = ""
    while time.perf_counter() - t < 90:
        try:
            state = node.admin.command("replSetGetStatus")["myState"]
            if state in (1, 2):
                break
        except PyMongoError:
            pass
        time.sleep(0.5)
    ctx.log("-", f"=> node cổng {port} trở lại, trạng thái {'PRIMARY' if state == 1 else 'SECONDARY'}")
    with open(logp, encoding="utf-8", errors="replace") as f:
        f.seek(pos)
        lines = mongo_recovery_lines(f)
    ctx.note("Nhật ký khôi phục của node bị kill (trích):")
    for ln in lines[:20]:
        ctx.log("-", ln[:260])
    ctx.metric("recovery_log", lines)
    ctx.check("Node bị kill trở lại replica set", state in (1, 2), True)
    node.close()
    # chờ cụm ổn định (node ưu tiên cao lấy lại PRIMARY) trước test tiếp theo
    t = time.perf_counter()
    while time.perf_counter() - t < 60:
        try:
            if primary_port(probe) == C.MONGO_BASE_PORT:
                break
        except PyMongoError:
            pass
        time.sleep(1)
    probe.close()
    A.end(), B.end()


# ============================================================================================== C2 / C3 helpers
def summarize(rows, key="orders_per_sec"):
    out = {}
    for cfg in dict.fromkeys(r["config"] for r in rows):
        v = [r[key] for r in rows if r["config"] == cfg]
        mean = st.mean(v)
        sd = st.stdev(v) if len(v) > 1 else 0.0
        out[cfg] = dict(config=cfg, n=len(v), median=round(st.median(v), 1), min=round(min(v), 1), max=round(max(v), 1),
                        stdev=round(sd, 2), cv_pct=round(100 * sd / mean, 1) if mean else 0.0)
    return out


def write_csv(ctx, name, rows):
    path = os.path.join(ctx.out_dir, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    ctx.tables.append(name)


def rotate(cfgs, rep):
    k = rep % len(cfgs)
    return cfgs[k:] + cfgs[:k]


ITEM = [dict(variant_id=101, location_id=3, quantity=1)]


# ============================================================================================== C2
MY_C2 = [("app_flush1", "App (câu lệnh từ ứng dụng), flush=1 + sync_binlog=1"),
         ("app_flush2", "App (câu lệnh từ ứng dụng), flush=2 + sync_binlog=0"),
         ("proc_flush1", "Stored procedure, flush=1 + sync_binlog=1")]
MG_C2 = [("txn_majority", "Transaction, w: majority"), ("txn_w1", "Transaction, w: 1"),
         ("notxn_majority", "Không transaction, w: majority"), ("notxn_w1", "Không transaction, w: 1")]


def my_prepare_big():
    my.reset()
    my.q("UPDATE inventory SET qty_on_hand = 1000000 WHERE variant_id = 101 AND location_id = 3")


@case("C2", "MySQL", "Thông lượng giao dịch Đặt hàng tuần tự theo cấu hình độ bền",
      "H1: nới độ bền (flush=2, sync_binlog=0) tăng thông lượng; H2: stored procedure (1 lượt gọi mạng) nhanh hơn "
      "câu lệnh từ ứng dụng mà không giảm độ bền.")
def c2_my(ctx):
    o = ctx.opts
    rows = []
    try:
        for rep in range(o.reps):
            for cfg, label in rotate(MY_C2, rep):
                my_prepare_big()
                flush, sync = ("2", "0") if cfg == "app_flush2" else ("1", "1")
                my.set_global("innodb_flush_log_at_trx_commit", flush)
                my.set_global("sync_binlog", sync)
                con = my.connect()
                prof = AM.find_customer_with_tier(con, 1)

                def one():
                    if cfg.startswith("proc"):
                        AM.place_order_proc(con, 1, 101, 3, 1, "12 Nguyễn Huệ")
                    else:
                        AM.place_order(con, 1, ITEM, "12 Nguyễn Huệ", profile=prof)
                for _ in range(o.warmup):
                    one()
                t = time.perf_counter()
                for _ in range(o.orders):
                    one()
                sec = time.perf_counter() - t
                con.close()
                n = my.q("SELECT COUNT(*) n FROM orders")[0]["n"] - 1
                rsv = my.q("SELECT qty_reserved r FROM inventory WHERE variant_id = 101 AND location_id = 3")[0]["r"]
                row = dict(lan=rep + 1, config=cfg, don=o.orders, giay=round(sec, 3), orders_per_sec=round(o.orders / sec, 1),
                           ms_don=round(1000 * sec / o.orders, 3), don_ghi=n, giu_cho=rsv,
                           dung=(n == rsv == o.orders + o.warmup))
                rows.append(row)
                ctx.log("-", f"lần {rep + 1} | {label:55} | {row['orders_per_sec']:7.1f} đơn/s | {row['ms_don']:.2f} ms/đơn")
    finally:
        my.set_global("innodb_flush_log_at_trx_commit", "1")
        my.set_global("sync_binlog", "1")
    write_csv(ctx, "C2-MY_raw.csv", rows)
    s = summarize(rows)
    write_csv(ctx, "C2-MY_summary.csv", list(s.values()))
    for cfg, label in MY_C2:
        ctx.metric(f"{cfg}", s[cfg])
        ctx.log("-", f"TỔNG HỢP | {label:55} | trung vị {s[cfg]['median']:.1f} [{s[cfg]['min']:.1f}; {s[cfg]['max']:.1f}] "
                     f"| CV {s[cfg]['cv_pct']}%")
    ctx.check("Mọi lần đo đều đúng (số đơn = số giữ chỗ = số đơn gửi)", all(r["dung"] for r in rows), True)
    ctx.check("H1: trung vị flush=2 / flush=1", round(s["app_flush2"]["median"] / s["app_flush1"]["median"], 2), "> 1",
              ok=s["app_flush2"]["median"] > s["app_flush1"]["median"])
    ctx.check("H2: trung vị procedure / câu lệnh từ ứng dụng", round(s["proc_flush1"]["median"] / s["app_flush1"]["median"], 2),
              "> 1", ok=s["proc_flush1"]["median"] > s["app_flush1"]["median"])


@case("C2", "MongoDB", "Thông lượng giao dịch Đặt hàng tuần tự theo write concern và có / không transaction",
      "H3: w: 1 nhanh hơn w: majority; H4: với w: majority, dùng transaction nhanh hơn không dùng (chỉ chờ nhân bản "
      "một lần lúc commit).")
def c2_mg(ctx):
    o = ctx.opts
    rows = []
    for rep in range(o.reps):
        for cfg, label in rotate(MG_C2, rep):
            mg.reset()
            mg.db.inventory.update_one({"_id": "101:3"}, {"$set": {"qty_on_hand": 1_000_000}})
            w = 1 if cfg.endswith("w1") else "majority"
            dbw = mg.client.get_database(C.DB, write_concern=WriteConcern(w=w))
            sess = mg.client.start_session()

            def one():
                if cfg.startswith("txn"):
                    sess.with_transaction(lambda s: M.place_order(dbw, s, 1, ITEM, "12 Nguyễn Huệ"),
                                          read_concern=mg.TXN["read_concern"], write_concern=WriteConcern(w=w))
                else:
                    M.place_order(dbw, None, 1, ITEM, "12 Nguyễn Huệ")
            for _ in range(o.warmup):
                one()
            t = time.perf_counter()
            for _ in range(o.orders):
                one()
            sec = time.perf_counter() - t
            sess.end_session()
            n = mg.db.orders.count_documents({}) - 1
            rsv = mg.db.inventory.find_one({"_id": "101:3"})["qty_reserved"]
            row = dict(lan=rep + 1, config=cfg, don=o.orders, giay=round(sec, 3), orders_per_sec=round(o.orders / sec, 1),
                       ms_don=round(1000 * sec / o.orders, 3), don_ghi=n, giu_cho=rsv, dung=(n == rsv == o.orders + o.warmup))
            rows.append(row)
            ctx.log("-", f"lần {rep + 1} | {label:40} | {row['orders_per_sec']:7.1f} đơn/s | {row['ms_don']:.2f} ms/đơn")
    write_csv(ctx, "C2-MG_raw.csv", rows)
    s = summarize(rows)
    write_csv(ctx, "C2-MG_summary.csv", list(s.values()))
    for cfg, label in MG_C2:
        ctx.metric(cfg, s[cfg])
        ctx.log("-", f"TỔNG HỢP | {label:40} | trung vị {s[cfg]['median']:.1f} [{s[cfg]['min']:.1f}; {s[cfg]['max']:.1f}] "
                     f"| CV {s[cfg]['cv_pct']}%")
    ctx.check("Mọi lần đo đều đúng", all(r["dung"] for r in rows), True)
    ctx.check("H3: trung vị w:1 / w:majority (có transaction)",
              round(s["txn_w1"]["median"] / s["txn_majority"]["median"], 2), "> 1",
              ok=s["txn_w1"]["median"] > s["txn_majority"]["median"])
    ctx.check("H4: trung vị có / không transaction (w: majority)",
              round(s["txn_majority"]["median"] / s["notxn_majority"]["median"], 2), "> 1",
              ok=s["txn_majority"]["median"] > s["notxn_majority"]["median"])


# ============================================================================================== C3
MY_C3 = [("cond", "Cập nhật có điều kiện (khóa dòng, giao dịch sau chờ)"),
         ("version_retry", "Version như app + tự thử lại"),
         ("version_app", "Version như app, KHÔNG thử lại (đúng hành vi hiện tại)")]


def c3_run_mysql(o, cfg):
    my.reset()
    my.q("UPDATE inventory SET qty_on_hand = %s WHERE variant_id = 101 AND location_id = 3", (o.threads * o.per_thread,))
    stats = dict(ok=0, rejected=0, retries=0, deadlocks=0)
    lock = threading.Lock()

    def worker(i):
        con = my.connect()
        prof = AM.find_customer_with_tier(con, 1 + i % 3)
        for _ in range(o.per_thread):
            while True:
                try:
                    AM.place_order(con, 1 + i % 3, ITEM, "x", reserve="cond" if cfg == "cond" else "version", profile=prof)
                    with lock:
                        stats["ok"] += 1
                    break
                except AM.AppError as e:
                    if e.code == "VERSION_CONFLICT" and cfg == "version_retry":
                        with lock:
                            stats["retries"] += 1
                        continue
                    with lock:
                        stats["rejected"] += 1
                    break
                except Exception as e:  # noqa: BLE001
                    if getattr(e, "args", [None])[0] == 1213:
                        with lock:
                            stats["deadlocks"] += 1
                            stats["retries"] += 1
                        continue
                    raise
        con.close()
    th = [threading.Thread(target=worker, args=(i,)) for i in range(o.threads)]
    t = time.perf_counter()
    for x in th:
        x.start()
    for x in th:
        x.join()
    sec = time.perf_counter() - t
    extra = None
    if cfg != "version_app":
        con = my.connect()
        try:
            AM.place_order(con, 1, ITEM, "x", reserve="cond" if cfg == "cond" else "version")
            extra = "chấp nhận"
        except AM.AppError as e:
            extra = e.code
        con.close()
    n = my.q("SELECT COUNT(*) n FROM orders")[0]["n"] - 1
    rsv = my.q("SELECT qty_reserved r FROM inventory WHERE variant_id = 101 AND location_id = 3")[0]["r"]
    return dict(config=cfg, giay=round(sec, 3), don_thanh_cong=stats["ok"], orders_per_sec=round(stats["ok"] / sec, 1),
                bi_tu_choi=stats["rejected"], thu_lai=stats["retries"], deadlock=stats["deadlocks"], don_ghi=n,
                giu_cho=rsv, don_vuot=extra, dung=(n == rsv == stats["ok"]))


@case("C3", "MySQL", "8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800",
      "Cập nhật có điều kiện: 800/800, không thử lại, đơn thứ 801 bị từ chối. Version như app: không bán vượt, nhưng "
      "nếu không thử lại thì nhiều đơn bị từ chối dù kho còn hàng.")
def c3_my(ctx):
    o = ctx.opts
    rows = []
    for rep in range(o.reps):
        for cfg, label in rotate(MY_C3, rep):
            r = c3_run_mysql(o, cfg)
            r = dict(lan=rep + 1, **r)
            rows.append(r)
            ctx.log("-", f"lần {rep + 1} | {label:58} | {r['don_thanh_cong']:4} đơn | {r['orders_per_sec']:6.1f} đơn/s | "
                         f"thử lại {r['thu_lai']:5} | từ chối {r['bi_tu_choi']:4} | đơn vượt: {r['don_vuot']}")
    write_csv(ctx, "C3-MY_raw.csv", rows)
    s = summarize(rows)
    total = o.threads * o.per_thread
    for cfg, label in MY_C3:
        rr = [r for r in rows if r["config"] == cfg]
        extra = dict(retries_median=st.median(r["thu_lai"] for r in rr), retries_min=min(r["thu_lai"] for r in rr),
                     retries_max=max(r["thu_lai"] for r in rr),
                     rejected_median=st.median(r["bi_tu_choi"] for r in rr), rejected_min=min(r["bi_tu_choi"] for r in rr),
                     rejected_max=max(r["bi_tu_choi"] for r in rr), ok_median=st.median(r["don_thanh_cong"] for r in rr))
        ctx.metric(cfg, {**s[cfg], **extra})
        ctx.log("-", f"TỔNG HỢP | {label:58} | trung vị {s[cfg]['median']:.1f} [{s[cfg]['min']:.1f}; {s[cfg]['max']:.1f}] đơn/s"
                     f" | thử lại trung vị {extra['retries_median']} | từ chối trung vị {extra['rejected_median']}")
    cond = [r for r in rows if r["config"] == "cond"]
    ver = [r for r in rows if r["config"] == "version_retry"]
    app = [r for r in rows if r["config"] == "version_app"]
    ctx.check("Cập nhật có điều kiện: [đơn thành công, thử lại, đơn thứ 801] mọi lần",
              sorted({(r["don_thanh_cong"], r["thu_lai"], r["don_vuot"]) for r in cond}), [(total, 0, "OUT_OF_STOCK")])
    ctx.check("Version + thử lại: đủ 800 đơn và đơn 801 bị từ chối mọi lần",
              all(r["don_thanh_cong"] == total and r["don_vuot"] == "OUT_OF_STOCK" for r in ver), True)
    ctx.check("Version như app, không thử lại: có đơn bị từ chối dù còn hàng", all(r["bi_tu_choi"] > 0 for r in app), True)
    ctx.check("Mọi lần: số đơn = số giữ chỗ (không bán vượt, không mất)", all(r["dung"] for r in rows), True)


@case("C3", "MongoDB", "8 luồng x 100 đơn cùng mua sofa Lawson 240 tại Kho Bình Dương, tồn đúng 800",
      "withTransaction tự thử lại khi WriteConflict: 800/800 đúng, đơn thứ 801 bị từ chối, nhưng nhiều lần thử lại.")
def c3_mg(ctx):
    o = ctx.opts
    rows = []
    total = o.threads * o.per_thread
    for rep in range(o.reps):
        mg.reset()
        mg.db.inventory.update_one({"_id": "101:3"}, {"$set": {"qty_on_hand": total}})
        stats = dict(ok=0, attempts=0, rejected=0)
        lock = threading.Lock()

        def worker(i):
            s = mg.client.start_session()
            for _ in range(o.per_thread):
                def cb(ss):
                    with lock:
                        stats["attempts"] += 1
                    return M.place_order(mg.db, ss, 1 + i % 3, ITEM, "x", reserve="cond")
                try:
                    s.with_transaction(cb, **mg.TXN)
                    with lock:
                        stats["ok"] += 1
                except M.AppError:
                    with lock:
                        stats["rejected"] += 1
            s.end_session()
        th = [threading.Thread(target=worker, args=(i,)) for i in range(o.threads)]
        t = time.perf_counter()
        for x in th:
            x.start()
        for x in th:
            x.join()
        sec = time.perf_counter() - t
        with mg.client.start_session() as s:
            try:
                s.with_transaction(lambda ss: M.place_order(mg.db, ss, 1, ITEM, "x", reserve="cond"), **mg.TXN)
                extra = "chấp nhận"
            except M.AppError as e:
                extra = e.code
        n = mg.db.orders.count_documents({}) - 1
        rsv = mg.db.inventory.find_one({"_id": "101:3"})["qty_reserved"]
        r = dict(lan=rep + 1, config="txn_cond", giay=round(sec, 3), don_thanh_cong=stats["ok"],
                 orders_per_sec=round(stats["ok"] / sec, 1), bi_tu_choi=stats["rejected"],
                 thu_lai=stats["attempts"] - stats["ok"] - stats["rejected"], deadlock=0, don_ghi=n, giu_cho=rsv,
                 don_vuot=extra, dung=(n == rsv == stats["ok"]))
        rows.append(r)
        ctx.log("-", f"lần {rep + 1} | withTransaction, cập nhật có điều kiện | {r['don_thanh_cong']:4} đơn | "
                     f"{r['orders_per_sec']:6.1f} đơn/s | thử lại {r['thu_lai']:5} | đơn vượt: {extra}")
    write_csv(ctx, "C3-MG_raw.csv", rows)
    s = summarize(rows)["txn_cond"]
    extra = dict(retries_median=st.median(r["thu_lai"] for r in rows), retries_min=min(r["thu_lai"] for r in rows),
                 retries_max=max(r["thu_lai"] for r in rows))
    ctx.metric("txn_cond", {**s, **extra})
    ctx.log("-", f"TỔNG HỢP | trung vị {s['median']:.1f} [{s['min']:.1f}; {s['max']:.1f}] đơn/s | thử lại trung vị "
                 f"{extra['retries_median']} [{extra['retries_min']}; {extra['retries_max']}]")
    ctx.check("Mọi lần: 800 đơn thành công và đơn 801 bị từ chối",
              all(r["don_thanh_cong"] == total and r["don_vuot"] == "OUT_OF_STOCK" for r in rows), True)
    ctx.check("Mọi lần có thử lại do WriteConflict", all(r["thu_lai"] > 0 for r in rows), True)
    ctx.check("Mọi lần: số đơn = số giữ chỗ", all(r["dung"] for r in rows), True)
