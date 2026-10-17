import json, random, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
users=[u for u in Path(sys.argv[1]).read_text().split() if u]
PROFILE=str(Path.home()/"Claude Code/reels-radar/data/pw-profile")
KEY="xdt_api__v1__feed__user_timeline_graphql_connection"
with sync_playwright() as p:
    ctx=p.chromium.launch_persistent_context(PROFILE, headless=True, viewport={"width":1280,"height":1400})
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    for u in users:
        rec={"u":u}
        tl=[]
        def on(r):
            try:
                if "graphql" in r.url and r.request.resource_type in ("xhr","fetch"):
                    t=r.text()
                    if KEY in t:
                        tl.append(json.loads(t))
            except Exception: pass
        page.on("response", on)
        try:
            resp=page.goto(f"https://www.instagram.com/{u}/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4500)
            rec["status"]=resp.status if resp else None
            rec["login"]="/accounts/login" in page.url
            body=page.inner_text("body")[:2500]
            rec["private_text"]=bool(re.search(r"This account is private|закрыт", body, re.I))
            rec["gone_text"]=bool(re.search(r"isn't available|недоступна|Sorry", body, re.I))
            m=page.query_selector('meta[property="og:description"]')
            rec["meta"]=m.get_attribute("content")[:120] if m else None
            rec["canvas"]=len(page.query_selector_all("header canvas"))
            edges=[]
            for d in tl:
                edges+= (d.get("data",{}).get(KEY,{}) or {}).get("edges",[])
            rec["timeline_edges"]=len(edges)
            rec["dates"]=sorted({time.strftime("%Y-%m-%d", time.gmtime(e["node"]["taken_at"])) for e in edges if e.get("node",{}).get("taken_at")}, reverse=True)[:4]
            rec["types"]=sorted({e["node"].get("product_type") for e in edges if e.get("node")})
            rec["collab_n"]=sum(1 for e in edges if e.get("node",{}).get("coauthor_producers"))
            # кнопка Похожие: ищем только по подписи, подписку не трогаем
            lab=page.eval_on_selector_all('svg[aria-label]', "e=>e.map(x=>x.getAttribute('aria-label'))")
            rec["svg_labels"]=sorted(set(l for l in lab if re.search(r"imilar|охож|uggest|ecommend", l or "")))
        except Exception as e:
            rec["error"]=repr(e)[:200]
        print(json.dumps(rec, ensure_ascii=False)[:800], flush=True)
        page.remove_listener("response", on)
        if rec.get("login") or rec.get("status") in (429,403):
            print("STOP"); break
        time.sleep(random.uniform(6,10))
    ctx.close()
