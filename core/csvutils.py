# core/csvutils.py
import csv
from django.http import StreamingHttpResponse

class Echo:  # memory-safe CSV streaming
    def write(self, value): return value

def stream_csv(rows_iterable, filename):
    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)
    resp = StreamingHttpResponse((writer.writerow(row) for row in rows_iterable),
                                 content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
