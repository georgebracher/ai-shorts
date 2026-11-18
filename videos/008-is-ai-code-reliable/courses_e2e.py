"""End to end on the courses page: python3 tests/courses_e2e.py BASE_URL [chromium|webkit]. Prints PASS/FAIL per check. Not run by pytest (needs a server and Playwright browsers)."""
import json, sys, time
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/courses/"
ENGINE = sys.argv[2] if len(sys.argv) > 2 else "chromium"
import os, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = os.environ.get("SHOTS", "/tmp/courses-shots") + "/"
os.makedirs(SHOTS, exist_ok=True)
import urllib.request  # public copy: courses.json comes from the site under test
def _load_courses(base):
    req = urllib.request.Request(base + 'courses.json', headers={'User-Agent': 'Mozilla/5.0 (course tests)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
courses = _load_courses(BASE)
def step(key):
    c, l, i = key.split("/"); course = next(x for x in courses if x["id"] == c)
    return next(x for x in course["lessons"] if x["id"] == l)["steps"][int(i)]
results = []
def ok(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:300]), flush=True)

def out_text(page):
    return page.locator("#outText").inner_text()

def wait_verdict(page, timeout=40000):
    page.wait_for_selector("#verdict .verdict", timeout=timeout)
    return page.locator("#verdict .verdict").first

def run_code(page, key, code):
    page.goto(BASE + "#" + key)
    page.wait_for_selector("#code")
    page.fill("#code", code)
    page.click("#run")
    return wait_verdict(page)

with sync_playwright() as p:
    browser = getattr(p, ENGINE).launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 860})
    ctx.add_init_script("try { localStorage.setItem('gbc_no_analytics', '1'); } catch (e) {}")   # my test runs stay out of the numbers
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    t = time.time()
    page.goto(BASE)
    page.wait_for_selector(".card")
    ok("home renders three course cards", page.locator(".card").count() == 3, page.locator(".card").count())
    page.screenshot(path=SHOTS + f"{ENGINE}-home.png")

    # first Run, including Python's first download
    t = time.time()
    v = run_code(page, "python-zero/l01_first_words/1", step("python-zero/l01_first_words/1")["solution"])
    ok(f"first code step passes with its solution ({time.time() - t:.1f}s incl. Python start)", "ok" in v.get_attribute("class"), v.inner_text())
    page.screenshot(path=SHOTS + f"{ENGINE}-step-pass.png")

    # a wrong answer shows the difference
    v = run_code(page, "python-zero/l01_first_words/1", 'print("nope")')
    ok("wrong answer gets a 'no' verdict with a diff", "no" in v.get_attribute("class") or "close" in v.get_attribute("class"), v.inner_text())
    page.screenshot(path=SHOTS + f"{ENGINE}-step-wrong.png")

    # an error names its line and explains it
    v = run_code(page, "python-zero/l01_first_words/1", 'print("hi)')
    ok("syntax error explained in plain English", "quote mark" in v.inner_text(), v.inner_text())
    ok("error line marked in the gutter", page.locator(".gutter div.err").count() == 1)

    # input(): the program waits, the learner types, it carries on
    key = "python-zero/l05_input/1"
    page.goto(BASE + "#" + key); page.wait_for_selector("#code")
    page.fill("#code", step(key)["solution"]); page.click("#run")
    page.wait_for_selector("#inbar.on", timeout=20000)
    for _ in range(200):
        if "?" in out_text(page): break
        page.wait_for_timeout(100)
    page.fill("#stdin", "Priya"); page.press("#stdin", "Enter")
    v = wait_verdict(page)
    ok("input() step: typed name used, then checked", "Hello Priya" in out_text(page) and "ok" in v.get_attribute("class"), out_text(page) + " | " + v.inner_text())

    # endless loop: Stop works, and Python comes back for the next Run
    key = "python-zero/l07_while/4"
    page.goto(BASE + "#" + key); page.wait_for_selector("#code")
    page.click("#run"); page.wait_for_timeout(1500)
    page.click("#stop")
    v = wait_verdict(page)
    ok("Stop ends an endless loop", "Stopped" in v.inner_text(), v.inner_text())
    t = time.time()
    v = run_code(page, "python-zero/l01_first_words/1", step("python-zero/l01_first_words/1")["solution"])
    ok(f"Python restarts after Stop ({time.time() - t:.1f}s)", "ok" in v.get_attribute("class"), v.inner_text())

    # endless loop with no Stop: the 15 second limit
    t = time.time()
    page.goto(BASE + "#python-zero/l07_while/4"); page.wait_for_selector("#code")
    page.click("#run")
    v = wait_verdict(page, timeout=40000)
    ok(f"endless loop stopped by the time limit ({time.time() - t:.1f}s)", "15 seconds" in v.inner_text(), v.inner_text())

    # a step with its own file
    key = next(f"python-zero/{l['id']}/{i}" for l in courses[0]["lessons"] for i, s in enumerate(l["steps"]) if s.get("files") and s["type"] == "code")
    v = run_code(page, key, step(key)["solution"])
    ok(f"file step {key} passes", "ok" in v.get_attribute("class"), v.inner_text())

    # a test-based check
    key = next(f"{c['id']}/{l['id']}/{i}" for c in courses[:2] for l in c["lessons"] for i, s in enumerate(l["steps"]) if s["type"] == "code" and "test" in s.get("check", {}))
    v = run_code(page, key, step(key)["solution"])
    ok(f"test-checked step {key} passes", "ok" in v.get_attribute("class"), v.inner_text())

    # hints then the answer
    page.goto(BASE + "#python-zero/l02_numbers/0"); page.wait_for_selector("#hintBtn")
    n = len(step("python-zero/l02_numbers/0")["hints"])
    for _ in range(n + 1): page.click("#hintBtn")
    ok(f"{n} hints then the answer", page.locator(".hint").count() == n + 1 and "the answer" in page.locator(".hint").nth(n).inner_text().lower(), page.locator(".hint").count())

    # SQL
    key = "sql-zero/l01_first_query/2"
    t = time.time()
    v = run_code(page, key, step(key)["solution"])
    ok(f"SQL step passes ({time.time() - t:.1f}s incl. sqlite3)", "ok" in v.get_attribute("class"), v.inner_text())
    ok("SQL results shown as a table", "row" in out_text(page), out_text(page)[:200])
    page.screenshot(path=SHOTS + f"{ENGINE}-sql.png")
    v = run_code(page, key, "SELECT nope FROM games;")
    ok("SQL error explained", "no column" in v.inner_text().lower() or "There's no column" in v.inner_text(), v.inner_text())

    # choice and predict steps
    key = "python-zero/l01_first_words/6"
    page.goto(BASE + "#" + key); page.wait_for_selector(".choice")
    page.locator(".choice").nth(step(key)["correct"]).click()
    ok("choice step marks right answer", "Yes" in page.locator("#fb").inner_text())

    # progress survives a reload
    page.goto(BASE + "#python-zero"); page.reload(); page.wait_for_selector(".lesson")
    first = page.locator(".lesson").first.inner_text()
    ok("progress kept after reload", "/" in first and not first.strip().endswith(f"0/{len(courses[0]['lessons'][0]['steps'])}"), first)

    # phone width
    m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    m.add_init_script("try { localStorage.setItem('gbc_no_analytics', '1'); } catch (e) {}")
    mp = m.new_page()
    mp.goto(BASE); mp.wait_for_selector(".card")
    mp.screenshot(path=SHOTS + f"{ENGINE}-phone-home.png", full_page=True)
    over = mp.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    ok("phone home has no sideways scroll", over <= 0, over)
    mp.goto(BASE + "#python-zero/l01_first_words/1"); mp.wait_for_selector("#code")
    mp.screenshot(path=SHOTS + f"{ENGINE}-phone-step.png", full_page=True)
    over = mp.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    ok("phone step has no sideways scroll", over <= 0, over)

    real = [e for e in errors if "posthog" not in e.lower()]
    ok("no console errors", not real, real[:5])
    browser.close()
print(f"{sum(r for _, r in results)}/{len(results)} passed on {ENGINE}")
