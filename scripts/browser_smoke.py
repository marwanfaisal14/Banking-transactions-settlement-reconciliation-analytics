"""Functional browser checks against a temporary local HTTP server."""
import argparse
import csv
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run(browser_path=None, screenshots=None):
    report = json.loads((ROOT / 'docs/data/report.json').read_text())
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'docs')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=browser_path, headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator('#dashboard')).to_be_visible()
            expect(page.locator('#match-rate')).to_have_text(f"{report['metrics']['USD']['match_rate_pct']:.2f}%")
            assert page.locator('.bar-stack').count() > 10
            for currency in ('AED', 'EGP', 'USD'):
                page.select_option('#currency', currency)
                expect(page.locator('#match-rate')).to_have_text(f"{report['metrics'][currency]['match_rate_pct']:.2f}%")
                expect(page.locator('#page-summary')).to_contain_text(currency)
            print('PASS: snapshot load, chart, and currency-isolated KPI values')

            page.select_option('#status-filter', 'MISSING_SETTLEMENT')
            expect(page.locator('#table-body tr')).to_have_count(1)
            expect(page.locator('#table-body')).to_contain_text('TXN-000001')
            page.locator('#table-body .review').click()
            expect(page.locator('#detail-dialog')).to_be_visible()
            expect(page.locator('#dialog-title')).to_have_text('TXN-000001')
            expect(page.locator('#dialog-content')).to_contain_text('Trace the processor reference')
            page.keyboard.press('Escape')
            with page.expect_download() as capture:
                page.click('#export')
            download = capture.value
            assert download.suggested_filename == 'exceptions-USD-2026-10-26.csv'
            with open(download.path(), newline='') as handle:
                rows = list(csv.DictReader(handle))
            assert len(rows) == 1 and rows[0]['reference'] == 'TXN-000001' and rows[0]['currency'] == 'USD'
            print('PASS: issue filtering, record follow-up, and actual filtered CSV download')

            page.click('#tab-transactions')
            expect(page.locator('#page-summary')).to_contain_text('1–8 of 400')
            page.click('#next')
            expect(page.locator('#page-summary')).to_contain_text('9–16 of 400')
            page.select_option('#status-filter', 'CURRENCY_MISMATCH')
            expect(page.locator('#table-body tr')).to_have_count(1)
            expect(page.locator('#table-body')).to_contain_text('—')
            page.locator('#table-body .review').click()
            expect(page.locator('#dialog-content')).to_contain_text('Incompatible actual amounts are not converted')
            page.keyboard.press('Escape')
            page.fill('#search', 'no-such-reference')
            expect(page.locator('#empty-state')).to_be_visible()
            expect(page.locator('#export')).to_be_disabled()
            page.fill('#search', '')
            page.locator('#tab-transactions').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#tab-batches')).to_have_attribute('aria-selected', 'true')
            expect(page.locator('#table-body tr')).to_have_count(8)
            print('PASS: pagination, currency mismatch display, empty state, and keyboard tabs')

            page.click('#guide')
            expect(page.locator('#dialog-content')).to_contain_text('No live bank connection')
            page.click('#close-dialog')
            page.click('#tab-exceptions')
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshots / 'dashboard-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth') <= 391
            expect(page.locator('#currency')).to_be_visible()
            page.locator('#table-body .review').first.click()
            expect(page.locator('#detail-dialog')).to_be_visible()
            page.keyboard.press('Escape')
            if screenshots:
                page.locator('.table-scroll').evaluate('(el) => el.scrollLeft = 0')
                page.evaluate('document.activeElement.blur()')
                page.screenshot(path=str(screenshots / 'dashboard-mobile.png'), full_page=True)
            print('PASS: methodology dialog, mobile layout, and mobile record inspection')

            page.route('**/data/report.json', lambda route: route.fulfill(status=503, body='unavailable'))
            page.reload()
            expect(page.locator('#load-error')).to_be_visible()
            page.unroute('**/data/report.json')
            page.click('#retry')
            expect(page.locator('#dashboard')).to_be_visible()
            assert not errors, errors
            print('PASS: data-load failure, retry recovery, and no uncaught browser errors')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default=None, help='Existing Chromium executable, otherwise Playwright default')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    run(args.browser, args.screenshots)
