# inventory/warranty.py
import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Optional

try:
    from bs4 import BeautifulSoup  # optional; we handle if missing
except Exception:
    BeautifulSoup = None  # type: ignore

log = logging.getLogger(__name__)

CARLCARE_BASE = "https://www.carlcare.com/mw/warranty-check"

@dataclass
class WarrantyResult:
    status: str
    expires_at: Optional[dt.date] = None
    raw: Optional[dict] = None


class CarlcareClient:
    """
    Minimal, resilient client. Does local imports so the app can start
    even if 'requests' (or bs4) isn't installed on the server.
    """
    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    def _requests(self):
        try:
            import requests  # local import to avoid hard dependency at import time
            return requests
        except Exception:
            return None

    def check(self, imei: str) -> WarrantyResult:
        req = self._requests()
        if not req:
            return WarrantyResult(status="SKIPPED", raw={"error": "requests_not_installed"})

        try:
            sess = req.Session()
            sess.headers.update({
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "en-US,en;q=0.9",
            })

            # open form for cookies
            try:
                sess.get(CARLCARE_BASE + "/", timeout=self.timeout)
            except Exception:
                pass

            # try posting with common payload keys
            res = None
            for data in ({"sn": imei}, {"imei": imei}):
                try:
                    r = sess.post(CARLCARE_BASE + "/", data=data, timeout=self.timeout, allow_redirects=True)
                    if r.ok:
                        res = r
                        break
                except Exception:
                    continue

            if not res or not res.ok:
                return WarrantyResult(status="UNKNOWN", raw={"error": "post_failed"})

            html = res.text
            text = None
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(" ", strip=True)
            else:
                # crude fallback: strip tags
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()

            # classify status
            if re.search(r"Warranty status\s+Under warranty", text, re.I):
                status = "UNDER_WARRANTY"
            elif re.search(r"Warranty status\s+Waiting to be activated", text, re.I):
                status = "WAITING_ACTIVATION"
            elif re.search(r"Please check the warranty in the country", text, re.I):
                status = "NOT_IN_COUNTRY"
            else:
                status = "UNKNOWN"

            # parse expiry date if present
            m = re.search(r"Warranty expiration date\s+(\d{4}-\d{2}-\d{2})", text)
            expires_at = None
            if m:
                y, mo, d = map(int, m.group(1).split("-"))
                expires_at = dt.date(y, mo, d)

            return WarrantyResult(status=status, expires_at=expires_at, raw={"html_len": len(html)})

        except Exception as e:
            log.exception("Carlcare check failed")
            return WarrantyResult(status="UNKNOWN", raw={"error": str(e)})
