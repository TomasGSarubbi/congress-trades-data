"""Scraper de la Cámara de Representantes (disclosures-clerk.house.gov).

Baja el índice anual de filings (ZIP con un .txt tab-delimited), filtra los
Periodic Transaction Reports (FilingType == 'P') presentados en los últimos
LOOKBACK_DAYS días, descarga cada PDF electrónico y lo parsea con pdfplumber.
Los PTR en papel (escaneados) se registran pero no se parsean.

Formato real de los PDFs electrónicos: cada transacción ocupa 1 o 2 líneas.
Línea núcleo:  "SP Bloom Energy Corporation - P 07/24/2026 08/21/2026 $1,000,001 -"
Continuación:  "Common Stock (BE) [ST] $5,000,000"
o todo en una: "SP Apple Inc. (AAPL) [ST] P 08/12/2026 08/20/2026 $1,001 - $15,000"
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

# Línea núcleo de una transacción: [owner] [asset...] TIPO fecha fecha $monto[-[$monto]]
CORE_RE = re.compile(
    r"^(?:(?P<owner>SP|DC|JT)\s+)?"
    r"(?P<pre>.*?)\s*"
    r"(?P<tx>P|S \(partial\)|S|E)\s+"
    r"(?P<d1>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<d2>\d{2}/\d{2}/\d{4})\s+"
    r"\$(?P<lo>[\d,]+)"
    r"(?:\s*-\s*\$?(?P<hi>[\d,]+))?"
    r"\s*-?\s*$"
)

# Líneas de encabezados, pies y metadatos que nunca son parte del activo.
NOISE_RE = re.compile(
    r"("
    r"^ID\b|^Owner\b|^Asset\b|^Transaction\b|^Type\b|^Date\b|^Notification\b"
    r"|^Amount\b|^Cap\.|Gains\s*>|^Filing\b|^F\s?S\s?:|^S\s?O\s?:|^D\s?:"
    r"|^Description\s?:|^Subholding|^Location\s?:|^Comments\s?:"
    r"|^Initial Public Offering|^\*\s?For the complete|^Page \d"
    r"|^PERIODIC TRANSACTION|^Clerk of the House|^Name\s?:|^Status\s?:"
    r"|^State/District|^Refer to|^wledge|^certification|^Digitally Signed"
    r"|^--$"
    r")",
    re.IGNORECASE,
)

TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)")
ATYPE_RE = re.compile(r"\[([A-Z]{2,3})\]")
AMOUNT_RE = re.compile(r"^\$?([\d,]{4,})$")

TX_TYPE_MAP = {"P": "Purchase", "S": "Sale (Full)", "S (partial)": "Sale (Partial)", "E": "Exchange"}
OWNER_MAP = {"SP": "Spouse", "DC": "Dependent", "JT": "Joint"}


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


def _clean_asset(raw):
    """Saca ticker, tipo de activo y basura del texto acumulado del activo."""
    ticker_m = TICKER_RE.search(raw)
    atype_m = ATYPE_RE.search(raw)
    s = TICKER_RE.sub("", raw)
    s = ATYPE_RE.sub("", s)
    s = re.sub(r"\$[\d,]+", "", s)          # montos que se colaron
    s = re.sub(r"\s+", " ", s).strip(" -–.")
    return s, (ticker_m.group(1) if ticker_m else None), (atype_m.group(1) if atype_m else "ST")


def _parse_ptr_pdf(content, member, filed_date, source_url):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    rows = []
    current = None  # transacción abierta esperando continuación

    def close(tx):
        if tx is None:
            return
        asset, ticker, atype = _clean_asset(tx["raw_asset"])
        if not asset and not ticker:
            return
        lo = f"${tx['lo']}"
        amount = f"{lo} - ${tx['hi']}" if tx.get("hi") else lo + " +"
        rows.append(
            {
                "chamber": "House",
                "member": member,
                "owner": OWNER_MAP.get(tx["owner"], "Self"),
                "ticker": ticker,
                "asset": asset,
                "asset_type": atype,
                "tx_type": TX_TYPE_MAP.get(tx["tx"], tx["tx"]),
                "tx_date": tx["d1"],
                "filed_date": filed_date,
                "amount": amount,
                "source": source_url,
            }
        )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if NOISE_RE.search(line):
            # Los metadatos (F S:, Description:, etc.) cierran la transacción abierta.
            close(current)
            current = None
            continue
        m = CORE_RE.match(line)
        if m:
            close(current)
            current = {
                "owner": m.group("owner"),
                "raw_asset": m.group("pre") or "",
                "tx": m.group("tx"),
                "d1": m.group("d1"),
                "d2": m.group("d2"),
                "lo": m.group("lo"),
                "hi": m.group("hi"),
            }
            # Si la línea núcleo ya trae el rango completo, se puede cerrar,
            # pero el nombre del activo puede seguir en la línea siguiente.
            continue
        if current is not None:
            # Línea de continuación: puede traer el resto del nombre,
            # el ticker y/o el monto superior del rango.
            if current.get("hi") is None:
                am = AMOUNT_RE.match(line.replace(" ", ""))
                if am:
                    current["hi"] = am.group(1)
                    continue
                # monto al final de la línea, con texto de activo antes
                tail = re.search(r"\$([\d,]{4,})\s*$", line)
                if tail:
                    current["hi"] = tail.group(1)
                    line = line[: tail.start()].strip()
            if line:
                current["raw_asset"] += " " + line
    close(current)
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
