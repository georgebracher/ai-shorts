"""Real-browser cancellation regressions. Run with BASE_URL and chromium or webkit."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip('/') + '/courses/'
ENGINE = sys.argv[2] if len(sys.argv) > 2 else 'chromium'
import urllib.request  # public copy: courses.json comes from the site under test
def _load_courses(base):
    req = urllib.request.Request(base + 'courses.json', headers={'User-Agent': 'Mozilla/5.0 (course tests)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
COURSES = _load_courses(BASE)
FIRST = 'python-zero/l01_first_words/1'
SOLUTION = COURSES[0]['lessons'][0]['steps'][1]['solution']
results = []


def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name, flush=True)


with sync_playwright() as pw:
    browser = getattr(pw, ENGINE).launch()
    context = browser.new_context()
    context.add_init_script("localStorage.setItem('gbc_no_analytics', '1')")
    page = context.new_page()

    def start(key, code):
        page.goto(BASE + '#' + key)
        page.wait_for_selector('#code')
        page.fill('#code', code)
        page.click('#run')

    def stop_and_recover(label):
        enabled = page.locator('#stop').is_enabled()
        check(label + ': Stop enabled', enabled)
        if not enabled:
            page.reload()
            return
        page.click('#stop')
        check(label + ': immediate stopped verdict', 'Stopped.' in page.locator('#verdict').inner_text())
        # Same page, with no reload or sleep to hide a race with the cancelled task.
        code = COURSES[0]['lessons'][4]['steps'][1]['solution'] if label == 'checker' else COURSES[2]['lessons'][0]['steps'][2]['solution']
        page.fill('#code', code)
        page.click('#run')
        if label == 'checker':
            page.wait_for_selector('#inbar.on')
            page.fill('#stdin', 'Sam')
            page.press('#stdin', 'Enter')
        page.wait_for_selector('#verdict .ok', timeout=12000)
        check(label + ': next Run passes', page.locator('#verdict .ok').count() == 1)

    loop = 'name=input("Name? ")\nif name == "Sam":\n    while True: pass\nprint("Hello " + name)'
    start('python-zero/l05_input/1', loop)
    page.wait_for_selector('#inbar.on')
    page.fill('#stdin', 'Ada')
    page.press('#stdin', 'Enter')
    page.wait_for_function('() => !state.run && PY.busy()')
    stop_and_recover('checker')

    start('sql-zero/l01_first_query/2', 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n;')
    page.wait_for_function('() => PY.busy()')
    stop_and_recover('SQL')

    # Delay the real runtime download to reproduce Stop before Python is ready.
    cold = context.new_page()
    cold.route('**/pyodide.asm.wasm', lambda route: (cold.wait_for_timeout(1200), route.continue_()))
    cold.goto(BASE + '#' + FIRST)
    cold.wait_for_selector('#code')
    cold.fill('#code', 'while True: pass')
    cold.click('#run')
    check('cold start: Python still loading', not cold.evaluate('PY.isReady'))
    cold.click('#stop')
    cold.fill('#code', SOLUTION)
    cold.click('#run')
    cold.wait_for_selector('#verdict .ok', timeout=12000)
    check('cold start: cancelled loop never starts; next Run passes', cold.locator('#verdict .ok').count() == 1)

    # Navigation cancels a running checker, so it cannot consume the next step's time budget.
    start('python-zero/l05_input/1', loop)
    page.wait_for_selector('#inbar.on')
    page.fill('#stdin', 'Ada')
    page.press('#stdin', 'Enter')
    page.wait_for_function('() => !state.run && PY.busy()')
    start(FIRST, SOLUTION)
    page.wait_for_selector('#verdict .ok', timeout=12000)
    check('navigation during check: next step passes without old timeout', page.locator('#verdict .ok').count() == 1)
    browser.close()

print(f'{sum(results)}/{len(results)} passed on {ENGINE}')
sys.exit(0 if all(results) else 1)
