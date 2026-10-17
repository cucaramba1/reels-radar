import json, random, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
users=[u for u in Path(sys.argv[1]).read_text().split() if u]
PROFILE=str(Path.home()/"Claude Code/reels-radar/data/pw-profile")
RING_JS = """() => {
  const img = document.querySelector('header img[alt*="profile picture"], header img[alt*="фото профиля"]');
  if (!img) return {img:false};
  let el = img, chain = [];
  for (let i = 0; i < 5 && el; i++, el = el.parentElement) {
    chain.push({tag: el.tagName, role: el.getAttribute('role'), canvas: el.querySelectorAll('canvas').length});
  }
  const wrap = img.closest('[role="button"]');
  return {img:true, chain, wrap_role_button: !!wrap, canvas_near: (img.parentElement.parentElement||img).querySelectorAll('canvas').length};
}"""
with sync_playwright() as p:
    ctx=p.chromium.launch_persistent_context(PROFILE, headless=True, viewport={"width":1280,"height":1400})
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    for u in users:
        rec={"u":u}
        resp=page.goto(f"https://www.instagram.com/{u}/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        if "/accounts/login" in page.url:
            print("STOP login"); break
        rec["ring"]=page.evaluate(RING_JS)
        if u=="mikhnesss":
            btn=page.query_selector('svg[aria-label="Similar accounts"]')
            got=[]
            def on(r):
                try:
                    if "graphql" in r.url and r.request.resource_type in ("xhr","fetch"):
                        t=r.text()
                        if "username" in t and ("similar" in t.lower() or "chaining" in t.lower() or "suggest" in t.lower()):
                            got.append(t)
                except Exception: pass
            page.on("response", on)
            if btn:
                btn.click(); page.wait_for_timeout(3500)
            rec["similar_clicked"]=bool(btn)
            names=set()
            for t in got:
                names|=set(re.findall(r'"username":"([A-Za-z0-9._]+)"', t))
            rec["similar_resp"]=len(got); rec["similar_names"]=sorted(names)[:12]
            vis=page.eval_on_selector_all('a[href^="/"][role="link"]', "e=>e.map(x=>x.getAttribute('href'))")
            rec["links_after_click"]=[v for v in vis if re.fullmatch(r"/[A-Za-z0-9._]+/", v or "")][:20]
            page.screenshot(path=str(Path(sys.argv[2])/"similar.png"))
            page.remove_listener("response", on)
        print(json.dumps(rec, ensure_ascii=False)[:1200], flush=True)
        time.sleep(random.uniform(6,10))
    ctx.close()
