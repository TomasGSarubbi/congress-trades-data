"""Orquestador: corre ambos scrapers, mergea y escribe data/.

Salidas (en data/):
- transactions.json : rolling de los últimos KEEP_DAYS días (por filed_date)
- latest.json       : transacciones NUEVAS respecto de la corrida anterior
- meta.json         : timestamp de última corrida y conteos
"""

import datetime as dt
import hashlib
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import house  # noqa: E402
import senate  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "7"))
KEEP_DAYS = int(os.environ.get("KEEP_DAYS", "120"))


def tx_id(tx):
    key = "|".join(
        str(tx.get(k, "")) for k in ("chamber", "member", "ticker", "asset", "tx_type", "tx_date", "amount", "owner")
    )
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def parse_date(s):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s %(levelname)s] %(message)s")
    os.makedirs(DATA_DIR, exist_ok=True)
    tx_path = os.path.join(DATA_DIR, "transactions.json")
    latest_path = os.path.join(DATA_DIR, "latest.json")
    meta_path = os.path.join(DATA_DIR, "meta.json")

    existing = load_json(tx_path, [])
    known_ids = {t["id"] for t in existing if "id" in t}

    new_txs = []
    errors = []
    for name, mod in (("senate", senate), ("house", house)):
        try:
            new_txs.extend(mod.fetch(LOOKBACK_DAYS))
        except Exception as e:
            logging.exception("Scraper %s falló", name)
            errors.append(f"{name}: {e}")

    for tx in new_txs:
        tx["id"] = tx_id(tx)

    fresh = [t for t in new_txs if t["id"] not in known_ids]
    merged = {t["id"]: t for t in existing}
    for t in new_txs:
        merged[t["id"]] = t

    cutoff = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    kept = [
        t for t in merged.values()
        if (parse_date(t.get("filed_date")) or dt.date.today()) >= cutoff
    ]
    kept.sort(key=lambda t: (parse_date(t.get("filed_date")) or dt.date.min, t.get("member", "")), reverse=True)

    with open(tx_path, "w") as f:
        json.dump(kept, f, indent=1, ensure_ascii=False)
    with open(latest_path, "w") as f:
        json.dump(fresh, f, indent=1, ensure_ascii=False)
    with open(meta_path, "w") as f:
        json.dump(
            {
                "last_run_utc": dt.datetime.utcnow().isoformat() + "Z",
                "new_transactions": len(fresh),
                "total_kept": len(kept),
                "lookback_days": LOOKBACK_DAYS,
                "errors": errors,
            },
            f,
            indent=1,
        )
    logging.info("Listo: %d nuevas, %d en rolling", len(fresh), len(kept))
    # Si ambos scrapers fallaron, salir con error para que el workflow avise.
    if errors and not new_txs:
        sys.exit(1)


if __name__ == "__main__":
    main()
