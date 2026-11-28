"""Saca la miniatura (1280x720) a partir de un HTML.  Uso: python3 -I mini.py miniaturas/empresa.html salida.png"""
import sys, os
from playwright.sync_api import sync_playwright
src, dst = sys.argv[1:3]
with sync_playwright() as p:
    a = ["--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1"]
    try: b = p.chromium.launch(channel="chrome", headless=True, args=a)
    except Exception: b = p.chromium.launch(headless=True, args=a)
    pg = b.new_page(viewport={"width": 1280, "height": 720}); pg.goto("file://" + os.path.abspath(src)); pg.evaluate("document.fonts.ready.then(()=>1)")
    pg.screenshot(path=dst); b.close()
print("miniatura:", dst)
