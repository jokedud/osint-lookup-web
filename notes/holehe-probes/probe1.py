import asyncio, httpx, sys, uuid
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36","Accept":"application/json, text/plain, */*","Accept-Language":"en-US,en;q=0.9"}
async def p(c,name,coro):
    try: r=await coro; print(name, r.status_code, r.text[:300].replace("\n"," "))
    except Exception as e: print(name,"EXC",type(e).__name__,e)
async def main(email):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=UA) as c:
        await asyncio.gather(
          p(c,"spotify",c.get("https://spclient.wg.spotify.com/signup/public/v1/account",params={"validate":"1","email":email})),
          p(c,"firefox",c.post("https://api.accounts.firefox.com/v1/account/status",json={"email":email})),
          p(c,"ms_live",c.post("https://login.live.com/GetCredentialType.srf",json={"username":email,"isOtherIdpSupported":True,"checkPhones":False,"isRemoteNGCSupported":True,"isCookieBannerShown":False,"isFidoSupported":True,"forceotclogin":False})),
          p(c,"ms_aad",c.post("https://login.microsoftonline.com/common/GetCredentialType",json={"Username":email})),
          p(c,"chess",c.get("https://www.chess.com/callback/email/available",params={"email":email})),
          p(c,"wordpress",c.get(f"https://public-api.wordpress.com/rest/v1.1/users/{email}/auth-options")),
          p(c,"imgur",c.post("https://imgur.com/signin/ajax_email_available",data={"email":email},headers={"X-Requested-With":"XMLHttpRequest"})),
          p(c,"komoot",c.post("https://www.komoot.com/v1/signin",json={"email":email,"reason":"header"})),
          p(c,"bitmoji",c.post("https://bitmoji.api.snapchat.com/api/user/find",data={"email":email})),
          p(c,"wattpad",c.get("https://www.wattpad.com/api/v3/users/validate",params={"email":email})),
          p(c,"zoho",c.post("https://accounts.zoho.com/signin/v2/lookup/"+email,data={"mode":"primary","cli_time":"1","servicename":"ZohoHome"})),
          p(c,"duolingo",c.get("https://www.duolingo.com/2017-06-30/users",params={"email":email})),
          p(c,"gravatar",c.get(f"https://en.gravatar.com/{__import__('hashlib').md5(email.encode()).hexdigest()}.json")),
          p(c,"pinterest",c.post("https://www.pinterest.com/_ngapi/v3/users/email_available/",json={"email":email})),
          p(c,"docker",c.get("https://hub.docker.com/v2/users/signup/check-email",params={"email":email})),
          p(c,"lastpass",c.get("https://lastpass.com/create_account.php",params={"check":"avail","skipcontent":"1","mistype":"1","username":email})),
          p(c,"venmo",c.get("https://venmo.com")),
          p(c,"strava",c.get("https://www.strava.com/athletes/email_unique",params={"email":email})),
          p(c,"deezer",c.get("https://www.deezer.com/ajax/gw-light.php",params={"method":"deezer.emailCheck","input":"3","api_version":"1.0","api_token":""})),
          p(c,"patreon",c.post("https://www.patreon.com/api/auth?include=user.null&fields[user]=[]&json-api-version=1.0",json={"data":{"type":"genericPatreonApi","attributes":{"patreon_auth":{"email":email,"allow_account_creation":False},"auth_context":"auth"},"relationships":{}}})),
          p(c,"adobe",c.post("https://auth.services.adobe.com/signin/v2/users/accounts",json={"username":email},headers={"X-IMS-ClientId":"adobedotcom2","Content-Type":"application/json"})),
        )
asyncio.run(main(sys.argv[1]))
