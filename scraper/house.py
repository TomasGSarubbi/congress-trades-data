"""Scraper de la Cámara de Representantes (disclosures-clerk.house.gov).

Baja el índice anual de filings (ZIP con un .txt tab-delimited), filtra los
Periodic Transaction Reports (FilingType == 'P') presentados en los últimos
LOOKBACK_DAYS días, descarga cada PDF electrónico y lo parsea con pdfplumber.
Los PTR en papel (escaneados) se registran pero no se parsean.
"""

import datetime as dt
import io
import logging
import re
import time
import zipfile

import pdfplumber
import requests

ROOT = "https://disclosures-clerk.house.gov"
ZIP_URL = ROOT + "/public_disc/financial-pdfs/{year}FD.zip"
PTR_PDF_URL = ROOT + "/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

RATE_LIMIT_SECS = 1.0
LOGGER = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Fila de transacción en el PDF electrónico, p. ej.:
# "SP Apple Inc. (AAPL) [ST] P 08/12/2026 08/20/2026 $1,001 - $15,000"
TX_RE = re.compile(
    r"^(?P<owner>SP|DC|JT)?\s*"
    r"(?P<asset>.+?)\s*"
    r"(?:\((?P<ticker>[A-Z][A-Z0-9.\-]{0,9})\))?\s*"
    r"(?:\[(?P<atype>[A-Z]{2,3})\])?\s+"
    r"(?P<tx>P|S|S \(partial\)|E)\s+"
    r"(?P<tx_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<notif_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<amount>\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*\+)?)"
)

TX_TYPE_MAP = {"P": "Purchase", "S": "Sale (Full)", "S (partial)": "Sale (Partial)", "E": "Exchange"}


def _get(url, session):
    time.sleep(RATE_LIMIT_SECS)
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    return resp


def _index_rows(year, session):
    """Lee el índice anual {year}FD.txt del ZIP oficial."""
    resp = _get(ZIP_URL.format(year=year), session)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    txt_name = next(n for n in zf.namelist() if n.endswith(".txt"))
    text = zf.read(txt_name).decode("utf-8", errors="replace")
    lines = text.splitlines()
    header = lines[0].split("\t")
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) == len(header):
            yield dict(zip(header, parts))


def _parse_ptr_pdf(content, member, filed_date, source_url):
    rows = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    # Une líneas partidas: los nombres de activos largos se cortan en varias líneas.
    merged, buffer = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        candidate = (buffer + " " + line).strip() if buffer else line
        if TX_RE.match(candidate):
            merged.append(candidate)
            buffer = ""
        elif TX_RE.match(line):
            merged.append(line)
            buffer = ""
        else:
            # Acumula posibles fragmentos de una fila; descarta encabezados obvios.
            if re.search(r"(ID Owner|Asset Transaction|Date Notification|Filing Status|Description|Amount|Cap\. Gains)", line):
                buffer = ""
            else:
                buffer = candidate if len(candidate) < 400 else ""
    for line in merged:
        m = TX_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        rows.append(
            {
                "chamber": "House",
                "member": member,
                "owner": {"SP": "Spouse", "DC": "Dependent", "JT": "Joint"}.get(d["owner"], "Self"),
                "ticker": d["ticker"],
                "asset": d["asset"].strip(" ."),
                "asset_type": d["atype"] or "ST",
                "tx_type": TX_TYPE_MAP.get(d["tx"], d["tx"]),
                "tx_date": d["tx_date"],
                "filed_date": filed_date,
                "amount": d["amount"].replace("  ", " "),
                "source": source_url,
            }
        )
    return rows


def fetch(lookback_days: int = 7):
    today = dt.date.today()
    start_date = today - dt.timedelta(days=lookback_days)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    years = {start_date.year, today.year}
    ptrs = []
    for year in sorted(years):
        try:
            for row in _index_rows(year, session):
                if row.get("FilingType") != "P":
                    continue
                try:
                    filed = dt.datetime.strptime(row["FilingDate"], "%m/%d/%Y").date()
                except (ValueError, KeyError):
                    continue
                if filed >= start_date:
                    ptrs.append(row)
        except Exception:
            LOGGER.exception("House: fallo leyendo índice %s", year)

    LOGGER.info("House: %d PTRs presentados desde %s", len(ptrs), start_date)
    txs, skipped = [], 0
    for row in ptrs:
        doc_id = row["DocID"]
        member = f"{row.get('First', '').strip()} {row.get('Last', '').strip()}".title()
        year = row["FilingDate"].split("/")[-1]
        url = PTR_PDF_URL.format(year=year, doc_id=doc_id)
        # DocIDs que empiezan con 8 o 7 suelen ser filings en papel escaneados.
        if doc_id.startswith(("8", "7")):
            skipped += 1
            continue
        try:
            resp = _get(url, session)
            parsed = _parse_ptr_pdf(resp.content, member, row["FilingDate"], url)
            if not parsed:
                LOGGER.warning("House: PDF sin filas parseables %s (%s)", doc_id, member)
            txs.extend(parsed)
        except Exception:
            LOGGER.exception("House: fallo con doc %s", doc_id)
    LOGGER.info("House: %d transacciones (%d en papel omitidos)", len(txs), skipped)
    return txs
