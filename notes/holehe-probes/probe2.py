import asyncio, httpx, sys, re, json
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
H={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"}
def C(): return httpx.AsyncClient(timeout=15, follow_redirects=True, headers=H)
async def github(e):
    async with C() as c:
        r=await c.get("https://github.com/signup")
        m=re.search(r'<auto-check src="/email_validity_checks".*?value="([^"]+)"',r.text,re.S) or re.search(r'email_validity_checks[^>]*>\s*<input[^>]*value="([^"]+)"',r.text,re.S)
        toks=re.findall(r'name="authenticity_token" value="([^"]+)"',r.text)
        tok=m.group(1) if m else (toks[0] if toks else "")
        r2=await c.post("https://github.com/email_validity_checks",data={"authenticity_token":tok,"value":e},headers={"Origin":"https://github.com","Referer":"https://github.com/signup"})
        return r2.status_code, r2.text[:200], bool(m), len(toks)
async def instagram(e):
    async with C() as c:
        await c.get("https://www.instagram.com/accounts/emailsignup/")
        tok=c.cookies.get("csrftoken")
        r=await c.post("https://www.instagram.com/api/v1/web/accounts/web_create_ajax/attempt/",data={"email":e,"first_name":"","username":"","opt_into_one_tap":"false"},headers={"X-CSRFToken":tok or "","X-IG-App-ID":"936619743392459","X-Requested-With":"XMLHttpRequest","Referer":"https://www.instagram.com/accounts/emailsignup/"})
        return r.status_code, r.text[:300], tok is not None
async def discord(e):
    async with C() as c:
        r=await c.post("https://discord.com/api/v9/auth/register",json={"email":e,"username":"zq8k2u1x9","global_name":"","password":"Xk29!dlsQwz","consent":True,"date_of_birth":"1994-03-04","gift_code_sku_id":None})
        return r.status_code, r.text[:300]
async def tumblr(e):
    async with C() as c:
        r=await c.get("https://www.tumblr.com/register")
        m=re.search(r'"API_TOKEN":"([^"]+)"',r.text)
        if not m: return "notoken", r.status_code
        r2=await c.post("https://www.tumblr.com/api/v2/register/account/validate",json={"email":e,"tumblelog":"zq8k2u1x9qq","password":"Xk29!dlsQwz"},headers={"Authorization":"Bearer "+m.group(1),"Origin":"https://www.tumblr.com"})
        return r2.status_code, r2.text[:300]
async def soundcloud(e):
    async with C() as c:
        r=await c.get("https://soundcloud.com/")
        cid=None
        for s in re.findall(r'<script crossorigin src="([^"]+)"',r.text)[::-1]:
            t=(await c.get(s)).text; m=re.search(r'client_id[:=]"(\w{32})"',t)
            if m: cid=m.group(1);break
        if not cid: return "nocid"
        r2=await c.get("https://api-auth.soundcloud.com/web-auth/identifier",params={"q":e,"client_id":cid})
        return r2.status_code, r2.text[:200]
async def imgur(e):
    async with C() as c:
        await c.get("https://imgur.com/register?redirect=%2Fuser")
        r=await c.post("https://imgur.com/signin/ajax_email_available",data={"email":e},headers={"X-Requested-With":"XMLHttpRequest","Origin":"https://imgur.com","Referer":"https://imgur.com/register?redirect=%2Fuser"})
        return r.status_code, r.text[:200]
async def lastfm(e):
    async with C() as c:
        await c.get("https://www.last.fm/join")
        tok=c.cookies.get("csrftoken")
        r=await c.post("https://www.last.fm/join/partial/validate",data={"csrfmiddlewaretoken":tok,"userName":"","email":e,"password":"","passwordConf":""},headers={"Referer":"https://www.last.fm/join","X-Requested-With":"XMLHttpRequest"})
        return r.status_code, r.text[:300], tok is not None
async def pinterest(e):
    async with C() as c:
        r=await c.get("https://www.pinterest.com/resource/EmailExistsResource/get/",params={"source_url":"/","data":json.dumps({"options":{"email":e},"context":{}})},headers={"X-Requested-With":"XMLHttpRequest","Accept":"application/json"})
        return r.status_code, r.text[:200]
async def codecademy(e):
    async with C() as c:
        r=await c.get("https://www.codecademy.com/register")
        m=re.search(r'name="csrf-token" content="([^"]+)"',r.text)
        return r.status_code, bool(m)
async def atlassian(e):
    async with C() as c:
        r=await c.post("https://id.atlassian.com/rest/check-username",json={"username":e})
        return r.status_code, r.text[:200]
async def vsco(e):
    async with C() as c:
        r=await c.get("https://api.vsco.co/2.0/users/email",params={"email":e},headers={"Authorization":"Bearer 7356455548d0a1d886db010883388d08be84d0c9"})
        return r.status_code, r.text[:200]
async def myspace(e):
    async with C() as c:
        r=await c.get("https://myspace.com/signup/email"); m=re.search(r'name="csrf" value="([^"]+)"',r.text) or re.search(r'"csrf":"([^"]+)"',r.text)
        r2=await c.post("https://myspace.com/ajax/account/validateemail",data={"email":e},headers={"Hash":m.group(1) if m else "","X-Requested-With":"XMLHttpRequest"})
        return r2.status_code, r2.text[:200]
async def hubspot(e):
    async with C() as c:
        r=await c.post("https://api.hubspot.com/login-api/v1/login",json={"email":e,"password":"Xk29!dlsQwz","rememberLogin":False})
        return r.status_code, r.text[:200]
async def ebay(e):
    async with C() as c:
        r=await c.get("https://signin.ebay.com/signin/")
        return r.status_code, len(r.text)
async def yahoo(e):
    async with C() as c:
        r=await c.get("https://login.yahoo.com/")
        ac=re.search(r'name="acrumb" value="([^"]+)"',r.text); sid=re.search(r'name="sessionIndex" value="([^"]+)"',r.text)
        if not ac: return "noacrumb", r.status_code
        r2=await c.post("https://login.yahoo.com/",data={"acrumb":ac.group(1),"sessionIndex":sid.group(1) if sid else "","username":e,"passwd":"","signin":"Next","persistent":"y"},headers={"X-Requested-With":"XMLHttpRequest","Origin":"https://login.yahoo.com","Referer":"https://login.yahoo.com/"})
        return r2.status_code, r2.text[:200]
async def docker(e):
    async with C() as c:
        r=await c.post("https://hub.docker.com/v2/users/signup/",json={"email":e,"username":"","password":""})
        return r.status_code, r.text[:200]
async def archive(e):
    async with C() as c:
        r=await c.post("https://archive.org/account/signup",data={"input_name":"email","input_value":e,"input_validator":"true","submit_by_js":"true"},headers={"X-Requested-With":"XMLHttpRequest"})
        return r.status_code, r.text[:200]
async def patreon(e):
    async with C() as c:
        r=await c.post("https://www.patreon.com/api/auth?include=user.null&fields[user]=[]&json-api-version=1.0",json={"data":{"type":"genericPatreonApi","attributes":{"patreon_auth":{"email":e,"allow_account_creation":False},"auth_context":"auth"},"relationships":{}}},headers={"Content-Type":"application/vnd.api+json"})
        d=r.json()["data"]["attributes"]; return r.status_code, {k:v for k,v in d.items() if v not in (None,False,"",[])}
async def gravatar3(e):
    import hashlib
    async with C() as c:
        r=await c.get("https://api.gravatar.com/v3/profiles/"+hashlib.sha256(e.encode()).hexdigest())
        return r.status_code, r.text[:100]
async def strava(e):
    async with C() as c:
        r=await c.get("https://www.strava.com/register/email_unique",params={"email":e})
        return r.status_code, r.text[:100]
async def main(e):
    fs=[github,instagram,discord,tumblr,soundcloud,imgur,lastfm,pinterest,codecademy,atlassian,vsco,myspace,hubspot,ebay,yahoo,docker,archive,patreon,gravatar3,strava]
    async def w(f):
        try: print(f.__name__, await f(e))
        except Exception as x: print(f.__name__,"EXC",type(x).__name__,str(x)[:100])
    await asyncio.gather(*[w(f) for f in fs])
asyncio.run(main(sys.argv[1]))
