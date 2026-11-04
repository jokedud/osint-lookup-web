import sys, json, trio, httpx, collections
from holehe.core import import_submodules, get_functions, launch_module
async def main(email):
    websites = get_functions(import_submodules("holehe.modules")); out=[]
    client = httpx.AsyncClient(timeout=20, follow_redirects=True)
    async with trio.open_nursery() as n:
        for w in websites: n.start_soon(launch_module, w, email, client, out)
    await client.aclose()
    return out
email=sys.argv[1]
out=trio.run(main,email)
c=collections.Counter("found" if o["exists"] else ("unknown" if o["rateLimit"] else "not_found") for o in out)
print(email, len(out), dict(c))
json.dump(out, open(f"/Users/devin/work/base_{email}.json","w"), indent=1)
