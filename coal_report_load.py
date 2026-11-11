"""Load the Daily/Weekly report's data lists from a workbook on the server.

    python coal_report_load.py "1 Calculation file - 20261110.xlsx" [weigh ready contracts]

For a Calculation file over the 64 MB upload limit. Same reading and the same
rule as the page's upload: each list found replaces the days the file covers
(Contract replaces the whole list). Run as www-data on the server.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app                      # noqa: E402
from app import coal_report                     # noqa: E402
from app.models import db, KVStore              # noqa: E402


def _kv(key, value=None):
    row = db.session.get(KVStore, key)
    if value is None:
        return row.value if row else None
    if row:
        row.value = value
    else:
        db.session.add(KVStore(key=key, value=value))
    db.session.commit()


def main(path, kinds):
    app = create_app()
    with app.app_context():
        with open(path, "rb") as f:
            res = coal_report.import_workbook(f, kinds, log=lambda m: print(datetime.now().strftime("%H:%M:%S"), m, flush=True))
        meta = json.loads(_kv("coalRptMeta_v1") or "{}")
        stamp = {"at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "by": "server load", "file": os.path.basename(path)[:120]}
        for k in kinds:
            if k not in res:
                continue
            r = res[k]
            if k == "contracts":
                _kv("coalRptContracts_v1", json.dumps(r.pop("data")))
            meta[k] = dict(stamp, **r)
        _kv("coalRptMeta_v1", json.dumps(meta))
        print("done", {k: v for k, v in meta.items() if k in kinds}, "missing:", res.get("missing"))
        print("now", coal_report.summary())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], tuple(sys.argv[2:]) or ("weigh", "ready", "contracts"))
