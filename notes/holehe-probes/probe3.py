import asyncio, httpx, sys, re, json
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
H={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"}
def C(): return httpx.AsyncClient(timeout=15, follow_redirects=True, headers=H)
async def ms(e):
    async with C() as c:
        r=await c.get("https://odc.officeapps.live.com/odc/emailhrd/getidp",params={"hm":"1","emailAddress":e})
        return r.status_code, r.text[:150]
async def ghpage(e):
    async with C() as c:
        r=await c.get("https://github.com/signup")
        i=r.text.find("email_validity"); return r.status_code, r.text[max(0,i-300):i+400] if i>=0 else "none"
async def yahoopage(e):
    async with C() as c:
        r=await c.get("https://login.yahoo.com/")
        return r.status_code, re.findall(r'<input[^>]+name="([^"]+)"',r.text)[:30]
async def zoho(e):
    async with C() as c:
        r=await c.get("https://accounts.zoho.com/signin")
        tok=c.cookies.get("iamcsr")
        r2=await c.post("https://accounts.zoho.com/signin/v2/lookup/"+e,data={"mode":"primary","cli_time":"1700000000000","servicename":"ZohoHome","serviceurl":"https://www.zoho.com/","service_language":"en"},headers={"X-ZCSRF-TOKEN":"iamcsrcoo="+(tok or ""),"Origin":"https://accounts.zoho.com"})
        return r2.status_code, r2.text[:200]
async def docker(e):
    async with C() as c:
        r=await c.post("https://hub.docker.com/v2/users/signup/check-email/",json={"email":e})
        return r.status_code, r.text[:150]
async def gitlab(e):
    async with C() as c:
        r=await c.get("https://gitlab.com/users/sign_up"); 
        r2=await c.get("https://gitlab.com/users/"+e+"/exists"); return r2.status_code, r2.text[:100]
async def dropbox(e):
    async with C() as c:
        r=await c.get("https://www.dropbox.com/login")
        return r.status_code
async def strava(e): return "skip"
async def mailru(e):
    async with C() as c:
        r=await c.post("https://account.mail.ru/api/v1/user/exists",data={"email":e}); return r.status_code, r.text[:150]
async def protonpks(e):
    async with C() as c:
        r=await c.get("https://api.protonmail.ch/pks/lookup",params={"op":"index","search":e}); return r.status_code, r.text[:80]
async def keybase(e):
    async with C() as c:
        r=await c.get("https://keybase.io/_/api/1.0/user/lookup.json",params={"email":e}); return r.status_code, r.text[:150]
async def lyft(e): return "skip"
async def picsart(e):
    async with C() as c:
        r=await c.get("https://api.picsart.com/users/email/existence",params={"email":e}); return r.status_code, r.text[:150]
async def flickr(e): return "skip"
async def main(e):
    fs=[ms,ghpage,yahoopage,zoho,docker,gitlab,mailru,protonpks,keybase,picsart]
    async def w(f):
        try: print(f.__name__, await f(e))
        except Exception as x: print(f.__name__,"EXC",type(x).__name__,str(x)[:100])
    await asyncio.gather(*[w(f) for f in fs])
asyncio.run(main(sys.argv[1]))
