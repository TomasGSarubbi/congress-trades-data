"""Scraper del Senado de EE.UU. (efdsearch.senate.gov).

Baja los Periodic Transaction Reports (PTR) presentados en los últimos
LOOKBACK_DAYS días y devuelve las transacciones normalizadas.
Los PTR presentados en papel (escaneados) se registran pero no se parsean.
"""

import datetime as dt
import logging
import time

import requests
from bs4 import BeautifulSoup

ROOT = "https://efdsearch.senate.gov"
LANDING_PAGE_URL = f"{ROOT}/search/home/"
SEARCH_PAGE_URL = f"{ROOT}/search/"
REPORTS_URL = f"{ROOT}/search/report/data/"

BATCH_SIZE = 100
RATE_LIMIT_SECS = 1.5
PAPER_PREFIX = "/search/view/paper/"

LOGGER = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _sleep():
    time.sleep(RATE_LIMIT_SECS)


def _csrf(client: requests.Session) -> str:
    """Acepta el agreement inicial y devuelve el token CSRF de la sesión."""
    _sleep()
    resp = client.get(LANDING_PAGE_URL)
    resp.raise_for_status()
    page = BeautifulSoup(resp.text, "lxml")
    token = page.find(attrs={"name": "csrfmiddlewaretoken"})["value"]
    _sleep()
    client.post(
        LANDING_PAGE_URL,
        data={"csrfmiddlewaretoken": token, "prohibition_agreement": "1"},
        headers={"Referer": LANDING_PAGE_URL},
    )
    return client.cookies.get("csrftoken") or client.cookies.get("csrf")


def _reports_page(client, offset, token, start_date):
    payload = {
        "start": str(offset),
        "length": str(BATCH_SIZE),
        "report_types": "[11]",  # 11 = Periodic Transaction Report
        "filer_types": "[]",
        "submitted_start_date": start_date.strftime("%m/%d/%Y") + " 00:00:00",
        "submitted_end_date": "",
        "candidate_state": "",
        "senator_state": "",
        "office_id": "",
        "first_name": "",
        "last_name": "",
        "csrfmiddlewaretoken": token,
    }
    _sleep()
    resp = client.post(REPORTS_URL, data=payload, headers={"Referer": SEARCH_PAGE_URL})
    resp.raise_for_status()
    return resp.json()["data"]


def _parse_ptr_html(client, link, filer, filed_date):
    """Parsea un PTR electrónico (tabla HTML) y devuelve las filas."""
    _sleep()
    resp = client.get(ROOT + link)
    if resp.url == LANDING_PAGE_URL:  # sesión vencida
        _csrf(client)
        _sleep()
        resp = client.get(ROOT + link)
    soup = BeautifulSoup(resp.text, "lxml")
    tbodies = soup.find_all("tbody")
    if not tbodies:
        return []
    rows = []
    for tr in tbodies[0].find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 8:
            continue
        tx_date, owner, ticker, asset_name, asset_type, tx_type, amount = (
            cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7],
        )
        rows.append(
            {
                "chamber": "Senate",
                "member": filer,
                "owner": owner,
                "ticker": ticker if ticker not in ("--", "") else None,
                "asset": asset_name,
                "asset_type": asset_type,
                "tx_type": tx_type,
                "tx_date": tx_date,
                "filed_date": filed_date,
                "amount": amount,
                "source": ROOT + link,
            }
        )
    return rows


def fetch(lookback_days: int = 7):
    start_date = dt.date.today() - dt.timedelta(days=lookback_days)
    client = requests.Session()
    client.headers.update({"User-Agent": UA})
    token = _csrf(client)

    reports, offset = [], 0
    while True:
        page = _reports_page(client, offset, token, start_date)
        reports.extend(page)
        if len(page) < BATCH_SIZE:
            break
        offset += BATCH_SIZE

    LOGGER.info("Senado: %d reportes presentados desde %s", len(reports), start_date)
    txs, skipped_paper = [], 0
    for row in reports:
        first, last, _, link_html, date_received = row[:5]
        filer = f"{first.strip()} {last.strip()}".title()
        a = BeautifulSoup(link_html, "lxml").a
        if a is None:
            continue
        link = a.get("href", "")
        if link.startswith(PAPER_PREFIX):
            skipped_paper += 1
            continue
        try:
            txs.extend(_parse_ptr_html(client, link, filer, date_received))
        except Exception:
            LOGGER.exception("Senado: fallo parseando %s", link)
    LOGGER.info("Senado: %d transacciones (%d PTR en papel omitidos)", len(txs), skipped_paper)
    return txs
