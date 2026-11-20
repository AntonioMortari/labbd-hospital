import asyncio, os, httpx

BASE = os.getenv("BASE_URL", "http://localhost:8080")


async def race(c):
    """500 recepcionistas disputando o MESMO leito: exatamente 1 pode vencer."""
    ids = [(await c.post("/patients", json={"name": f"P{i}", "priority": 1})).json()["id"]
           for i in range(500)]
    res = await asyncio.gather(*[c.post("/beds/001/allocate", params={"patient_id": p}) for p in ids])
    ok = sum(1 for x in res if x.status_code == 200)
    print(f"[RACE] sucessos={ok} (esperado=1) conflitos={sum(1 for x in res if x.status_code == 409)}")
    await c.post("/beds/001/release")


async def main():
    limits = httpx.Limits(max_connections=300)
    async with httpx.AsyncClient(base_url=BASE, timeout=30, limits=limits) as c:
        await race(c)

asyncio.run(main())
