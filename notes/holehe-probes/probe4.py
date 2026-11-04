import asyncio, httpx, sys, re, json
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
H={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"}
def C(): return httpx.AsyncClient(timeout=15, follow_redirects=True, headers=H)
async def codecademy(e):
    async with C() as c:
        r=await c.get("https://www.codecademy.com/register?redirect=%2F"); m=re.search(r'name="csrf-token" content="([^"]+)"',r.text)
        r2=await c.post("https://www.codecademy.com/register/validate",json={"user":{"email":e}},headers={"X-CSRF-Token":m.group(1) if m else "","Accept":"application/json","Origin":"https://www.codecademy.com"})
        return r2.status_code, r2.text[:200]
async def codepen(e):
    async with C() as c:
        r=await c.get("https://codepen.io/accounts/signup/user/free"); m=re.search(r'name="csrf-token" content="([^"]+)"',r.text)
        r2=await c.post("https://codepen.io/accounts/duplicate_check",data={"attribute":"email","value":e,"context":"user"},headers={"X-CSRF-Token":m.group(1) if m else "","X-Requested-With":"XMLHttpRequest"})
        return r.status_code, r2.status_code, r2.text[:200]
async def smule(e):
    async with C() as c:
        r=await c.get("https://www.smule.com/user/check_email"); m=re.search(r'name="csrf-token" content="([^"]+)"',r.text) or re.search(r'<meta content="([^"]+)" name="csrf-token"',r.text)
        r2=await c.post("https://www.smule.com/user/check_email",data={"email":e},headers={"X-CSRF-Token":m.group(1) if m else ""})
        return r.status_code, r2.status_code, r2.text[:200]
async def issuu(e):
    async with C() as c:
        r=await c.get("https://issuu.com/call/signup/check-email/"+e); return r.status_code, r.text[:150]
async def rocketreach(e):
    async with C() as c:
        r=await c.get("https://rocketreach.co/v1/validateEmail",params={"email_address":e}); return r.status_code, r.text[:150]
async def vivino(e):
    async with C() as c:
        r=await c.post("https://www.vivino.com/api/login",json={"email":e,"password":"e"},headers={"Accept":"application/json","X-Requested-With":"XMLHttpRequest"}); return r.status_code, r.text[:150]
async def evernote(e):
    async with C() as c:
        r=await c.get("https://www.evernote.com/Login.action"); return r.status_code, "hpts" in r.text, len(r.text)
async def bmc(e):
    async with C() as c:
        r=await c.get("https://www.buymeacoffee.com/"); return r.status_code, "bmc_csrf_token" in r.text
async def strava(e):
    async with C() as c:
        r=await c.get("https://www.strava.com/register/free"); return r.status_code
async def garmin(e): return "skip"
async def myfitnesspal(e):
    async with C() as c:
        r=await c.get("https://api.myfitnesspal.com/v2/users/validate",params={"email":e}); return r.status_code, r.text[:150]
async def eventbrite(e): return "ok"
async def xing(e): return "skip"
async def quora(e): return "skip"
async def flickr(e): return "ok"
async def main(e):
    fs=[codecademy,codepen,smule,issuu,rocketreach,vivino,evernote,bmc,strava,myfitnesspal]
    async def w(f):
        try: print(f.__name__, await f(e))
        except Exception as x: print(f.__name__,"EXC",type(x).__name__,str(x)[:100])
    await asyncio.gather(*[w(f) for f in fs])
asyncio.run(main(sys.argv[1]))
