# core/sqlite_udf.py
from __future__ import annotations
import logging
import math
from django.db import connection

log = logging.getLogger("db.udf")

def _guard(fn, *, default=None):
    """Wrap a Python function used as an SQLite UDF so it never raises."""
    def inner(*args):
        try:
            return fn(*args)
        except Exception as e:
            # Log full context; return NULL (None) or a supplied default
            log.exception("SQLite UDF error in %s args=%r: %s", fn.__name__, args, e)
            return default
    return inner

# ---- Example primitives you likely use in analytics/predictions ----

def _to_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None

def _to_int(x):
    if x is None or x == "":
        return None
    try:
        return int(x)
    except Exception:
        return None

def _safe_div(a, b):
    a = _to_float(a)
    b = _to_float(b)
    if a is None or b in (None, 0.0):
        return None
    return a / b

def _predict_linear(x, x1, y1, x2, y2):
    """Simple linear interpolation/extrapolation; returns None if bad inputs."""
    x  = _to_float(x)
    x1 = _to_float(x1); y1 = _to_float(y1)
    x2 = _to_float(x2); y2 = _to_float(y2)
    if None in (x, x1, y1, x2, y2):
        return None
    denom = (x2 - x1)
    if denom == 0:
        return None
    return y1 + ((x - x1) * (y2 - y1) / denom)

def _regexp(expr, val):
    import re
    if expr is None or val is None:
        return 0
    return 1 if re.search(expr, str(val)) else 0

def register_sqlite_udfs():
    """Idempotent: safe to call multiple times."""
    if connection.vendor != "sqlite":
        return
    try:
        connection.create_function("TO_FLOAT", 1, _guard(_to_float))
        connection.create_function("TO_INT", 1, _guard(_to_int))
        connection.create_function("SAFE_DIV", 2, _guard(_safe_div))
        connection.create_function("PREDICT_LINEAR", 5, _guard(_predict_linear))
        connection.create_function("REGEXP", 2, _guard(_regexp, default=0))
    except Exception:
        # If a function is already registered or connection isn't ready
        log.debug("register_sqlite_udfs() skipped/partial; functions may already be registered.", exc_info=True)
