import sys, trio, httpx, traceback
from holehe.core import import_submodules, get_functions
names=set(sys.argv[2:])
async def run1(w,email,client):
    out=[]
    try:
        with trio.fail_after(25): await w(email,client,out)
        print(w.__name__, "OK", out[0]["exists"], out[0]["rateLimit"], out[0].get("others"))
    except Exception as e:
        tb=traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ else None
        print(w.__name__, "EXC", type(e).__name__, str(e)[:120], tb.lineno if tb else "")
async def main(email):
    ws=[w for w in get_functions(import_submodules("holehe.modules")) if not names or w.__name__ in names]
    client=httpx.AsyncClient(timeout=20, follow_redirects=True)
    async with trio.open_nursery() as n:
        for w in ws: n.start_soon(run1,w,email,client)
trio.run(main,sys.argv[1])
