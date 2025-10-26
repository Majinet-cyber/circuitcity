import re
IMEI_RE = re.compile(r'\b\d{15}\b')
EMAIL_RE = re.compile(r'([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')

class RedactPIIFilter:
    def filter(self, record):
        msg = str(record.getMessage())
        msg = IMEI_RE.sub(lambda m: f"IMEI:****{m.group(0)[-4:]}", msg)
        msg = EMAIL_RE.sub(lambda m: f"{m.group(1)[0]}***@{m.group(2)}", msg)
        record.msg = msg
        record.args = ()
        return True


