"""Phiên MongoDB (ClientSession) có in timeline; nạp lại dữ liệu chuẩn."""
import threading
import time

from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from . import config as C
from . import mongo_model as M

client = MongoClient(C.MONGO_URI, serverSelectionTimeoutMS=30000)
db = client[C.DB]

TXN = dict(read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority"))


def version():
    return client.server_info()["version"]


def reset():
    M.reset(db)


def describe_error(e):
    code = getattr(e, "code", None)
    name = ""
    det = getattr(e, "details", None) or {}
    if isinstance(det, dict):
        name = det.get("codeName", "")
    labels = [lb for lb in ("TransientTransactionError", "UnknownTransactionCommitResult") if
              hasattr(e, "has_error_label") and e.has_error_label(lb)]
    msg = name or str(e).split(",")[0][:120]
    return f"ERROR {code} {msg}" + (f" {labels}" if labels else "")


class Res:
    def __init__(self, value=None, error=None, waited=0.0):
        self.value, self.error, self.waited = value, error, waited

    @property
    def ok(self):
        return self.error is None

    @property
    def code(self):
        return getattr(self.error, "code", None)

    def labels(self):
        return [lb for lb in ("TransientTransactionError", "UnknownTransactionCommitResult")
                if self.error is not None and hasattr(self.error, "has_error_label") and self.error.has_error_label(lb)]


def show(v):
    if v is None:
        return "null"
    if hasattr(v, "matched_count"):
        return f"matched {v.matched_count}, modified {v.modified_count}"
    if hasattr(v, "inserted_id"):
        return f"inserted {v.inserted_id}"
    return str(v)


class Sess:
    def __init__(self, ctx, lane, quiet=False):
        self.ctx, self.lane, self.quiet = ctx, lane, quiet
        self.s = client.start_session()

    def _log(self, text):
        if not self.quiet and self.ctx is not None:
            self.ctx.log(self.lane, text)

    def start(self, **kw):
        opts = dict(TXN)
        opts.update(kw)
        self.s.start_transaction(**opts)
        rc = opts["read_concern"].level
        wc = opts["write_concern"].document.get("w")
        self._log(f"session.startTransaction({{ readConcern: \"{rc}\", writeConcern: {{ w: {wc!r} }} }})"
                  .replace("'", "\""))

    def op(self, desc, fn, show_result=True):
        self._log(desc)
        try:
            v = fn(self.s)
            if show_result:
                self._log("=> " + show(v))
            return Res(v)
        except (PyMongoError, M.AppError) as e:
            self._log("=> " + (describe_error(e) if isinstance(e, PyMongoError) else f"Lỗi ứng dụng {e.code}"))
            return Res(error=e)

    def commit(self):
        return self.op("session.commitTransaction()", lambda s: s.commit_transaction() or "commit OK")

    def abort(self):
        return self.op("session.abortTransaction()", lambda s: s.abort_transaction() or "abort OK")

    def bg(self, desc, fn):
        self._log(desc + " (đang chờ...)")
        h = _Bg(self, fn)
        h.start()
        return h

    def end(self):
        try:
            if self.s.in_transaction:
                self.s.abort_transaction()
        except PyMongoError:
            pass
        self.s.end_session()


class _Bg(threading.Thread):
    def __init__(self, sess, fn):
        super().__init__(daemon=True)
        self.sess, self.fn, self.res = sess, fn, None

    def run(self):
        t = time.perf_counter()
        try:
            v = self.fn(self.sess.s)
            self.res = Res(v)
        except (PyMongoError, M.AppError) as e:
            self.res = Res(error=e)
        self.res.waited = time.perf_counter() - t

    def wait(self, timeout=120):
        self.join(timeout)
        r = self.res
        txt = describe_error(r.error) if r.error is not None else show(r.value)
        self.sess._log(f"=> {txt} (sau khi chờ {r.waited:.2f}s)")
        return r


__all__ = ["client", "db", "reset", "version", "Sess", "OperationFailure", "TXN"]
