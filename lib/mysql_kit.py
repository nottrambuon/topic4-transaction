"""Phiên MySQL có in timeline, chạy lệnh ở luồng nền (để quan sát chờ khóa), nạp lại dữ liệu chuẩn."""
import os
import subprocess
import threading
import time

import pymysql
import pymysql.cursors

from . import config as C

SETUP_FILES = ["mysql_schema.sql", "mysql_data.sql", "mysql_procedures.sql"]


def connect(db=True, **kw):
    args = dict(C.MYSQL, autocommit=True, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    if db:
        args["database"] = C.DB
    args.update(kw)
    return pymysql.connect(**args)


def admin():
    if C.MYSQL_ADMIN_SOCKET:
        return pymysql.connect(unix_socket=C.MYSQL_ADMIN_SOCKET, user="root", autocommit=True,
                               charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    return None


def cli(sql_text):
    r = subprocess.run(C.MYSQL_CLI, input=sql_text, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"mysql CLI lỗi: {r.stderr.strip()}")
    return r.stdout


def reset():
    """Xóa và tạo lại database luxury_furniture: schema của app + index + dữ liệu mẫu + procedure."""
    text = ""
    for f in SETUP_FILES:
        with open(os.path.join(C.SETUP_DIR, f), encoding="utf-8") as fh:
            text += fh.read() + "\n"
    cli(text)


def q(sql, args=None, db=True):
    con = connect(db=db)
    try:
        with con.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        con.close()


def set_global(name, value):
    a = admin()
    if a:
        with a.cursor() as cur:
            cur.execute(f"SET GLOBAL {name} = {value}")
        a.close()
    else:
        cli(f"SET GLOBAL {name} = {value};")


def one_line(sql):
    return " ".join(sql.split())


def fmt_rows(rows):
    if rows is None:
        return ""
    if not rows:
        return "(0 dòng)"
    out = []
    for r in rows:
        out.append(", ".join(f"{k}={_v(v)}" for k, v in r.items()))
    return "\n".join(out)


def _v(v):
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return f"{int(v):,}".replace(",", ".") if v == int(v) else str(v)
    except Exception:  # noqa: BLE001
        pass
    return v


class Result:
    def __init__(self, rows=None, affected=None, error=None, waited=0.0):
        self.rows, self.affected, self.error, self.waited = rows, affected, error, waited

    @property
    def code(self):
        return self.error.args[0] if self.error is not None and self.error.args else None

    @property
    def ok(self):
        return self.error is None

    def first(self, key=None):
        if not self.rows:
            return None
        return self.rows[0] if key is None else self.rows[0][key]


class Sess:
    """Một connection = một phiên (như một cửa sổ mysql)."""

    def __init__(self, ctx, lane, isolation=None, lock_wait_timeout=None, quiet=False):
        self.ctx, self.lane, self.quiet = ctx, lane, quiet
        self.con = connect()
        if lock_wait_timeout is not None:
            self.x(f"SET SESSION innodb_lock_wait_timeout = {lock_wait_timeout}")
        if isolation:
            self.x(f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation}")

    def _log(self, text):
        if not self.quiet and self.ctx is not None:
            self.ctx.log(self.lane, text)

    def _run(self, sql, args):
        try:
            with self.con.cursor() as cur:
                n = cur.execute(sql, args)
                rows = cur.fetchall() if cur.description else None
                return Result(rows=list(rows) if rows is not None else None, affected=None if rows is not None else n)
        except pymysql.MySQLError as e:
            return Result(error=e)

    def _describe(self, r):
        if r.error is not None:
            msg = r.error.args[1] if len(r.error.args) > 1 else str(r.error)
            return f"=> ERROR {r.code}: {msg}"
        if r.rows is not None:
            return "=> " + fmt_rows(r.rows).replace("\n", "\n   ")
        return f"=> {r.affected} row(s) affected"

    def x(self, sql, args=None, show=True):
        """Chạy một câu lệnh, in lệnh và kết quả. Không ném lỗi: lỗi trả về trong Result."""
        if show:
            self._log(one_line(sql) if args is None else one_line(sql) + f"   -- tham số {tuple(args)}")
        r = self._run(sql, args)
        if show:
            self._log(self._describe(r))
        return r

    def bg(self, sql, args=None):
        """Gửi lệnh ở luồng nền (lệnh có thể bị chặn vì chờ khóa). Gọi .wait() để lấy kết quả."""
        self._log(one_line(sql) + " (đang chờ...)")
        h = _Bg(self, sql, args)
        h.start()
        return h

    def close(self):
        try:
            self.con.close()
        except Exception:  # noqa: BLE001
            pass


class _Bg(threading.Thread):
    def __init__(self, sess, sql, args):
        super().__init__(daemon=True)
        self.sess, self.sql, self.args = sess, sql, args
        self.result = None

    def run(self):
        t = time.perf_counter()
        r = self.sess._run(self.sql, self.args)
        r.waited = time.perf_counter() - t
        self.result = r

    def wait(self, timeout=120):
        self.join(timeout)
        r = self.result
        self.sess._log(f"{self.sess._describe(r)} (sau khi chờ {r.waited:.2f}s)")
        return r
