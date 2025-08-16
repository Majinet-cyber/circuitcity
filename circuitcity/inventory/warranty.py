import datetime as dt
import logging
import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

CARLCARE_BASE = "https://www.carlcare.com/mw/warranty-check"

@dataclass
class WarrantyResult:
    status: str
    expires_at: Optional[dt.date] = None
    raw: dict = None

class CarlcareClient:
    def __init__(self, timeout=12):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def check(self, imei: str) -> WarrantyResult:
        try:
            # open form for cookies
            self.session.get(CARLCARE_BASE + "/", timeout=self.timeout)

            # try posting
            payloads = [{"sn": imei}, {"imei": imei}]
            res = None
            for data in payloads:
                try:
                    res = self.session.post(
                        CARLCARE_BASE + "/", 
                        data=data, 
                        timeout=self.timeout, 
                        allow_redirects=True
                    )
                    if res.ok:
                        break
                except Exception:
                    continue
            if not res or not res.ok:
                return WarrantyResult(status="UNKNOWN", raw={"error": "post_failed"})

            html = res.text
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)

            if re.search(r"Warranty status\s+Under warranty", text, re.I):
                status = "UNDER_WARRANTY"
            elif re.search(r"Warranty status\s+Waiting to be activated", text, re.I):
                status = "WAITING_ACTIVATION"
            elif re.search(r"Please check the warranty in the country", text, re.I):
                status = "NOT_IN_COUNTRY"
            else:
                status = "UNKNOWN"

            m = re.search(r"Warranty expiration date\s+(\d{4}-\d{2}-\d{2})", text)
            expires_at = None
            if m:
                y, mo, d = map(int, m.group(1).split("-"))
                expires_at = dt.date(y, mo, d)

            return WarrantyResult(status=status, expires_at=expires_at, raw={"html_len": len(html)})

        except Exception as e:
            log.exception("Carlcare check failed")
            return WarrantyResult(status="UNKNOWN", raw={"error": str(e)})
