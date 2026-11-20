"""Khung chạy test: đăng ký test, ghi timeline hai phiên A/B, kiểm tra tự động, ghi log và JSON."""
import json
import os
import time
import traceback

CASES = []


class Case:
    def __init__(self, cid, dbms, title, hypothesis, fn, destructive=False):
        self.cid, self.dbms, self.title, self.hypothesis, self.fn = cid, dbms, title, hypothesis, fn
        self.scenario = cid[0]
        self.key = f"{cid}-{'MY' if dbms == 'MySQL' else 'MG'}"
        self.destructive = destructive


def case(cid, dbms, title, hypothesis, destructive=False):
    def deco(fn):
        CASES.append(Case(cid, dbms, title, hypothesis, fn, destructive))
        return fn
    return deco


class Ctx:
    """Ngữ cảnh của một test: đồng hồ, timeline, các phép kiểm tra và số đo."""

    def __init__(self, case_, opts, log_path, out_dir):
        self.case, self.opts, self.out_dir = case_, opts, out_dir
        self.t0 = time.perf_counter()
        self.lines, self.checks, self.metrics, self.tables = [], [], {}, []
        self._f = open(log_path, "w", encoding="utf-8")

    def now(self):
        return time.perf_counter() - self.t0

    def _w(self, line):
        self.lines.append(line)
        self._f.write(line + "\n")
        self._f.flush()
        print(line, flush=True)

    def log(self, lane, text):
        pad = {"A": "", "B": "    ", "-": ""}.get(lane, "")
        for i, part in enumerate(str(text).split("\n")):
            stamp = f"[t={self.now():6.2f}s] " if i == 0 else " " * 12
            self._w(f"{stamp}{pad}{lane} | {part}")

    def step(self, text):
        self._w("")
        self._w(f"  >> {text}")

    def note(self, text):
        self._w(f"  -- {text}")

    def check(self, what, observed, expected, ok=None, why=""):
        if ok is None:
            ok = observed == expected
        ok = bool(ok)
        self.checks.append(dict(what=what, observed=observed, expected=str(expected), ok=ok, why=why))
        self._w(f"  [{'KHỚP' if ok else 'LỆCH'} ] {what}: quan sát = {observed} | kỳ vọng {expected}"
                + (f" ({why})" if why else ""))
        return ok

    def metric(self, key, value):
        self.metrics[key] = value

    def close(self):
        self._f.close()


def run_case(c, opts, log_dir):
    log_path = os.path.join(log_dir, f"{c.key}.log")
    out_dir = os.path.dirname(log_dir)
    ctx = Ctx(c, opts, log_path, out_dir)
    res = dict(key=c.key, cid=c.cid, dbms=c.dbms, title=c.title, hypothesis=c.hypothesis,
               log=os.path.relpath(log_path, out_dir), checks=[], metrics={}, tables=[])
    ctx._w("=" * 100)
    ctx._w(f"[{c.key}] {c.title} ({c.dbms})")
    ctx._w(f"Giả thuyết: {c.hypothesis}")
    if c.destructive and not opts.allow_crash:
        res.update(verdict="SKIP", reason="cần --allow-crash (test kill -9 server)", seconds=0)
        ctx._w("  => SKIP (cần --allow-crash)")
        ctx.close()
        return res
    t = time.perf_counter()
    try:
        c.fn(ctx)
        verdict = "PASS" if ctx.checks and all(k["ok"] for k in ctx.checks) else "FAIL"
    except Exception as e:  # noqa: BLE001
        verdict = "ERROR"
        ctx._w("  !! " + "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        res["reason"] = f"{type(e).__name__}: {e}"
    res.update(verdict=verdict, checks=ctx.checks, metrics=ctx.metrics, tables=ctx.tables,
               seconds=round(time.perf_counter() - t, 2))
    ok = sum(k["ok"] for k in ctx.checks)
    ctx._w("")
    ctx._w(f"  => {verdict} ({ok}/{len(ctx.checks)} kiểm tra khớp, {res['seconds']}s)")
    ctx.close()
    return res


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
