"""Chạy bộ test Transaction MySQL (InnoDB) vs MongoDB (WiredTiger) và xuất báo cáo.

Ví dụ:
    python run.py                     # A, B, C2, C3 trên cả hai hệ (C1 bị bỏ qua vì kill -9 server)
    python run.py A                   # chỉ Kịch bản A
    python run.py A2 B3               # chỉ test A2 và B3
    python run.py --dbms mysql B      # Kịch bản B, chỉ MySQL
    python run.py --allow-crash C1    # crash test (kill -9 mysqld / PRIMARY)
    python run.py --quick             # C2/C3 cỡ nhỏ (chạy thử nhanh)
    python run.py --list              # liệt kê test
"""
import argparse
import datetime
import os
import platform
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _s in (sys.stdout, sys.stderr):  # Windows: in tiếng Việt kể cả khi chuyển output ra file
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from lib import config as C  # noqa: E402
from lib import framework as F  # noqa: E402
from tests import scenario_a, scenario_b, scenario_c  # noqa: E402,F401


def parse():
    p = argparse.ArgumentParser(description="Bộ test Transaction MySQL vs MongoDB")
    p.add_argument("select", nargs="*", help="Kịch bản (A, B, C) hoặc mã test (A1, B3, C2...). Bỏ trống = tất cả")
    p.add_argument("--dbms", choices=["mysql", "mongodb", "both"], default="both")
    p.add_argument("--allow-crash", action="store_true", help="cho phép C1 (kill -9 server)")
    p.add_argument("--reps", type=int, default=5, help="số lần lặp cho C2/C3 (mặc định 5)")
    p.add_argument("--orders", type=int, default=1000, help="số đơn mỗi cấu hình ở C2 (mặc định 1000)")
    p.add_argument("--threads", type=int, default=8, help="số luồng ở C3 (mặc định 8)")
    p.add_argument("--per-thread", type=int, default=100, help="số đơn mỗi luồng ở C3 (mặc định 100)")
    p.add_argument("--warmup", type=int, default=50, help="số đơn chạy nóng máy, không tính giờ (mặc định 50)")
    p.add_argument("--quick", action="store_true", help="C2/C3 cỡ nhỏ: 200 đơn, 4 luồng x 50, 1 lần")
    p.add_argument("--list", action="store_true")
    o = p.parse_args()
    if o.quick:
        o.orders, o.threads, o.per_thread, o.reps, o.warmup = 200, 4, 50, 1, 20
    return o


def selected(opts):
    out = []
    for c in F.CASES:
        if opts.dbms != "both" and c.dbms.lower() != opts.dbms:
            continue
        if opts.select and not any(s.upper() in (c.scenario, c.cid, c.key) for s in opts.select):
            continue
        out.append(c)
    return out


def environment(cases):
    env = dict(time=datetime.datetime.now().isoformat(timespec="seconds"), python=platform.python_version(),
               os=platform.platform(), cpu_count=os.cpu_count())
    try:
        with open("/proc/meminfo") as f:
            env["ram_gb"] = round(int(f.readline().split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    if any(c.dbms == "MySQL" for c in cases):
        from lib import mysql_kit as my
        r = my.q("SELECT VERSION() AS version, @@transaction_isolation AS isolation, "
                 "@@innodb_flush_log_at_trx_commit AS flush_log_at_trx_commit, @@sync_binlog AS sync_binlog, "
                 "@@log_bin AS log_bin, @@innodb_lock_wait_timeout AS lock_wait_timeout, "
                 "@@innodb_deadlock_detect AS deadlock_detect", db=False)[0]
        env["mysql"] = {k: str(v) for k, v in r.items()}
    if any(c.dbms == "MongoDB" for c in cases):
        from lib import mongo_kit as mg
        a = mg.client.admin
        st = a.command("replSetGetStatus")
        env["mongodb"] = dict(
            version=mg.version(), replica_set=st["set"],
            members=[f"{m['name']} {m['stateStr']}" for m in st["members"]],
            transactionLifetimeLimitSeconds=a.command({"getParameter": 1, "transactionLifetimeLimitSeconds": 1})
            ["transactionLifetimeLimitSeconds"],
            maxTransactionLockRequestTimeoutMillis=a.command(
                {"getParameter": 1, "maxTransactionLockRequestTimeoutMillis": 1})["maxTransactionLockRequestTimeoutMillis"],
            defaultWriteConcern=a.command({"getDefaultRWConcern": 1}).get("defaultWriteConcern"))
    try:
        import pymongo
        import pymysql
        env["drivers"] = dict(pymysql=pymysql.__version__, pymongo=pymongo.version)
    except ImportError:
        pass
    return env


def fmt_val(v):
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 10000:
        return f"{v:,}"
    return str(v)


def write_summary(path, env, results, opts):
    L = ["# Kết quả bộ test Transaction: MySQL (InnoDB) vs MongoDB (WiredTiger)", ""]
    L.append(f"Chạy lúc {env['time']} · {env['os']} · {env.get('cpu_count')} CPU · {env.get('ram_gb', '?')} GB RAM")
    if "mysql" in env:
        m = env["mysql"]
        L.append(f"- MySQL {m['version']}: isolation {m['isolation']}, innodb_flush_log_at_trx_commit="
                 f"{m['flush_log_at_trx_commit']}, sync_binlog={m['sync_binlog']}, log_bin={m['log_bin']}")
    if "mongodb" in env:
        g = env["mongodb"]
        L.append(f"- MongoDB {g['version']}: replica set {g['replica_set']} ({'; '.join(g['members'])}), "
                 f"transactionLifetimeLimitSeconds={g['transactionLifetimeLimitSeconds']}")
    L.append(f"- Tham số C2/C3: {opts.reps} lần lặp, {opts.orders} đơn/cấu hình (C2), {opts.threads} luồng × "
             f"{opts.per_thread} đơn (C3), {opts.warmup} đơn chạy nóng")
    n = {v: sum(r["verdict"] == v for r in results) for v in ("PASS", "FAIL", "ERROR", "SKIP")}
    L += ["", f"**Tổng: {len(results)} test · PASS {n['PASS']} · FAIL {n['FAIL']} · ERROR {n['ERROR']} · "
              f"SKIP {n['SKIP']}**", "",
          "| Test | Hệ | Nội dung | Kiểm tra khớp | Kết luận | Thời gian (s) |", "|---|---|---|---|---|---|"]
    for r in results:
        ok = sum(k["ok"] for k in r["checks"])
        L.append(f"| [{r['key']}](#{r['key'].lower()}) | {r['dbms']} | {r['title']} | {ok}/{len(r['checks'])} | "
                 f"**{r['verdict']}** | {r.get('seconds', '')} |")
    L += ["", "## Chi tiết từng test", ""]
    for r in results:
        L += [f"### {r['key']}", "", f"**{r['title']}** ({r['dbms']}) · kết luận **{r['verdict']}** · "
              f"log: [`{r['log']}`]({r['log']})", "", f"*Giả thuyết:* {r['hypothesis']}", ""]
        if r.get("reason"):
            L += [f"Lý do: {r['reason']}", ""]
        if r["checks"]:
            L += ["| Đại lượng đo | Quan sát | Kỳ vọng | Khớp | Ghi chú |", "|---|---|---|---|---|"]
            for k in r["checks"]:
                L.append(f"| {k['what']} | {fmt_val(k['observed'])} | {k['expected']} | "
                         f"{'✓' if k['ok'] else '✗'} | {k['why']} |")
            L.append("")
        if r.get("tables"):
            L += ["Bảng số liệu: " + ", ".join(f"[`{t}`]({t})" for t in r["tables"]), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main():
    opts = parse()
    cases = selected(opts)
    if opts.list or not cases:
        for c in F.CASES:
            print(f"{c.key:6} {c.dbms:8} {c.title}{' [cần --allow-crash]' if c.destructive else ''}")
        if not cases and not opts.list:
            print("\nKhông có test nào khớp lựa chọn.")
        return
    run_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(C.RESULTS_DIR, run_id)
    log_dir = os.path.join(out, "logs")
    os.makedirs(log_dir, exist_ok=True)
    env = environment(cases)
    F.dump_json(os.path.join(out, "environment.json"), env)
    print(f"Chạy {len(cases)} test. Kết quả ghi vào {out}")
    results = [F.run_case(c, opts, log_dir) for c in cases]
    F.dump_json(os.path.join(out, "results.json"), dict(environment=env, options=vars(opts), cases=results))
    write_summary(os.path.join(out, "summary.md"), env, results, opts)
    latest = os.path.join(C.RESULTS_DIR, "latest")
    shutil.rmtree(latest, ignore_errors=True)
    shutil.copytree(out, latest)
    print("\n" + "=" * 100)
    print(f"{'Test':7} {'Hệ':8} {'Khớp':>6}  Kết luận  Nội dung")
    for r in results:
        ok = sum(k["ok"] for k in r["checks"])
        print(f"{r['key']:7} {r['dbms']:8} {ok:>2}/{len(r['checks']):<3}  {r['verdict']:8}  {r['title']}")
    print(f"\nBáo cáo: {os.path.join(out, 'summary.md')} (bản sao mới nhất: {latest})")
    sys.exit(0 if all(r["verdict"] in ("PASS", "SKIP") for r in results) else 1)


if __name__ == "__main__":
    main()
