"""Extended real-browser course checks: BASE_URL [chromium|webkit]."""
import json, pathlib, sys, time
from playwright.sync_api import sync_playwright
BASE=sys.argv[1].rstrip('/')+'/courses/'
ENGINE=sys.argv[2] if len(sys.argv)>2 else 'chromium'
ROOT=pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS=pathlib.Path('/tmp/courses-audit-artifacts'); ARTIFACTS.mkdir(exist_ok=True)
import urllib.request  # public copy: courses.json comes from the site under test
def _load_courses(base):
    req = urllib.request.Request(base + 'courses.json', headers={'User-Agent': 'Mozilla/5.0 (course tests)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
courses=_load_courses(BASE)
steps={f"{c['id']}/{l['id']}/{i}":s for c in courses for l in c['lessons'] for i,s in enumerate(l['steps'])}
key='python-zero/l01_first_words/1'
results=[]
def record(name,cond,detail=''):
    results.append([name,bool(cond),str(detail)[:600]])
    print(('PASS ' if cond else 'FAIL ')+name+' '+str(detail)[:300],flush=True)
with sync_playwright() as pw:
    browser=getattr(pw,ENGINE).launch()
    ctx=browser.new_context(viewport={'width':1280,'height':860})
    ctx.add_init_script("localStorage.setItem('gbc_no_analytics','1')")
    page=ctx.new_page();page.set_default_timeout(25000)
    def visit(k=key):
        page.goto(BASE+'#'+k);page.wait_for_selector('#code')
    def start(code,k=key):
        visit(k);page.fill('#code',code);page.click('#run')
    def verdict():
        page.wait_for_selector('#verdict .verdict',timeout=40000)
        return page.locator('#verdict').inner_text()
    def output():return page.locator('#outText').inner_text()
    def recover(label):
        start(steps[key]['solution']);verdict();record('Run again after '+label,page.locator('#verdict .ok').count()==1)
    # Type ahead while actual Python is busy, not a mocked worker.
    start('import time\ntime.sleep(1)\na=input("Name? ")\nprint("Hello",a)')
    page.wait_for_selector('#inbar.on');page.fill('#stdin','Ada');page.press('#stdin','Enter')
    verdict();record('input typed before prompt', 'Hello Ada' in output(),output())
    start('import time\ntime.sleep(1)\na=input("Name? ")\nprint("Hello",a)')
    page.wait_for_selector('#inbar.on')
    for v in ['Ada','unused','extra']:page.fill('#stdin',v);page.press('#stdin','Enter')
    verdict();record('extra input does not change result','Hello Ada' in output() and 'Hello unused' not in output(),output())
    start('for i in range(3):\n    print(i, input("Word? "))')
    page.wait_for_selector('#inbar.on')
    for v in ['red','green','blue']:page.fill('#stdin',v);page.press('#stdin','Enter')
    verdict();record('input inside loop',all(x in output() for x in ['0 red','1 green','2 blue']),output())
    start('import random\nprint("seed", random.random())\nname=input("Name? ")\nprint(name)')
    page.wait_for_function("() => document.querySelector('#outText').textContent.includes('seed')")
    first=output().splitlines()[0];page.fill('#stdin','Ada');page.press('#stdin','Enter');verdict()
    record('random prefix stable on replay',output().splitlines()[0]==first,output())
    for label,code in [('endless','while True: pass'),('bare except','try:\n    while True: pass\nexcept:\n    while True: pass'),('waiting input','input("Wait? ")')]:
        start(code);page.wait_for_selector('#stop:enabled');page.click('#stop');v=verdict()
        record('Stop '+label,'Stopped.' in v,v);recover(label)
    for label,code,needle in [('flood','while True: print("x")','far too much'),('recursion','def f(): f()\nf()','calling itself'),('os exit','import os; os._exit(0)',None),('sys exit','import sys; sys.exit()','print'),('bare except timeout','try:\n    while True: pass\nexcept:\n    while True: pass','15 seconds')]:
        start(code);v=verdict();record(label,needle is None or needle in v,v+' OUTPUT '+output()[:100]);recover(label)
    start('input("Wait? ")');page.wait_for_selector('#inbar.on');page.wait_for_timeout(16000)
    record('waiting input stays usable after 15 seconds',page.locator('#stop').is_enabled() and page.locator('#inbar.on').count()==1)
    page.click('#stop');verdict();recover('long input wait')
    start('open("audit-marker.txt","w").write("test")');verdict()
    start('import os\nprint(os.path.exists("audit-marker.txt"))');verdict();record('fresh folder each run',output().strip()=='False',output())
    # Check-only loop: the interactive run receives safe input, fixture supplies Sam.
    checkkey='python-zero/l05_input/1'
    code='name=input("What is your name? ")\nif name == "Sam":\n    while True: pass\nprint("Hello " + name)'
    start(code,checkkey);page.wait_for_selector('#inbar.on');page.fill('#stdin','Ada');page.press('#stdin','Enter')
    page.wait_for_function("() => !state.run && PY.busy()")
    record('Stop enabled during check',page.locator('#stop').is_enabled())
    if page.locator('#stop').is_enabled():page.click('#stop');v=verdict();record('Stop check ends promptly','Stopped' in v,v)
    else:v=verdict();record('check timeout returns verdict','never finished' in v,v)
    recover('check interrupt or timeout')
    # Each SQL lesson, syntax and fresh database.
    for lesson in courses[2]['lessons']:
        i,s=next((i,s) for i,s in enumerate(lesson['steps']) if s['type']=='code')
        k='sql-zero/'+lesson['id']+'/'+str(i);start(s['solution'],k);v=verdict()
        record('SQL '+lesson['id'],page.locator('#verdict .ok').count()==1,v)
    sqlkey='sql-zero/l01_first_query/2'
    start('SELEC * FROM games;',sqlkey);v=verdict();record('SQL syntax error','SQL couldn' in v,v)
    start('DROP TABLE games;',sqlkey);verdict();start(steps[sqlkey]['solution'],sqlkey);verdict()
    record('SQL database fresh after DROP',page.locator('#verdict .ok').count()==1)
    # All step kinds, including both predict controls.
    for kind in ['read','choice','predict-text','predict-choice']:
        k,s=next((k,s) for k,s in steps.items() if (s['type']==kind if kind in ['read','choice'] else s['type']=='predict' and bool(s.get('choices'))==(kind=='predict-choice')))
        page.goto(BASE+'#'+k);page.wait_for_selector('#next')
        if kind=='read':page.click('#next')
        elif kind=='choice':page.locator('.choice').nth(s['correct']).click()
        elif kind=='predict-text':page.fill('#guess',s['answer']);page.click('#guessBtn')
        else:page.locator('.choice').nth(next(i for i,v in enumerate(s['choices']) if v.strip()==s['answer'].strip())).click()
        page.wait_for_timeout(100)
        record('complete '+kind,page.evaluate('(k)=>!!state.progress.done[k]',k))
    recover('progress setup');page.reload();page.wait_for_selector('#code')
    record('progress survives reload',page.evaluate('(k)=>!!state.progress.done[k]',key))
    page.evaluate("localStorage.clear()");page.reload();page.wait_for_selector('#code')
    record('clear storage resets progress',page.evaluate('Object.keys(state.progress.done).length')==0)
    private=browser.new_context();private.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}})")
    pp=private.new_page();pp.goto(BASE+'#'+key);pp.wait_for_selector('#code');pp.fill('#code',steps[key]['solution']);pp.click('#run');pp.wait_for_selector('#verdict .ok',timeout=40000)
    record('storage throws: can run and pass',pp.locator('#verdict .ok').count()==1)
    page.set_viewport_size({'width':390,'height':844});visit();page.locator('#run').scroll_into_view_if_needed()
    geometry=page.evaluate("""() => ({overflow:document.documentElement.scrollWidth-innerWidth,runVisible:document.elementFromPoint(...(() => {let r=document.querySelector('#run').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()).closest('#run')!==null})""")
    page.screenshot(path=str(ARTIFACTS/('phone-audit-'+ENGINE+'.png')),full_page=True)
    record('390px overflow and uncovered Run',geometry['overflow']==0 and geometry['runVisible'],geometry)
    browser.close()
print(f'{sum(r[1] for r in results)}/{len(results)} passed',flush=True)
(ARTIFACTS/('adversarial-'+ENGINE+'.json')).write_text(json.dumps(results,indent=2))

sys.exit(0 if all(r[1] for r in results) else 1)
