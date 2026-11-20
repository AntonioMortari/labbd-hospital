import os, time, uuid, json, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
from pydantic import BaseModel, Field
import redis.asyncio as redis
from scripts import CALL_NEXT, ALLOCATE_BED, RELEASE_BED
import inspecao

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TOTAL_BEDS = int(os.getenv("TOTAL_BEDS", "50"))
QUEUE, RECENT, CHANNEL = "triage:queue", "panel:recent", "panel:events"

pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=200, decode_responses=True)
r = redis.Redis(connection_pool=pool)
call_next = allocate_bed = release_bed = None


@asynccontextmanager
async def lifespan(app):
    global call_next, allocate_bed, release_bed
    call_next = r.register_script(CALL_NEXT)
    allocate_bed = r.register_script(ALLOCATE_BED)
    release_bed = r.register_script(RELEASE_BED)
    # Semeia os leitos de forma idempotente (várias réplicas podem rodar isso ao mesmo tempo)
    pipe = r.pipeline()
    for i in range(1, TOTAL_BEDS + 1):
        bid = f"{i:03d}"
        pipe.hsetnx(f"bed:{bid}", "status", "livre")
        pipe.hsetnx("beds:init", bid, 1)
    await pipe.execute()
    ids = [f"{i:03d}" for i in range(1, TOTAL_BEDS + 1)]
    pipe = r.pipeline()
    for bid in ids:
        st = await r.hget(f"bed:{bid}", "status")
        pipe.sadd("beds:free" if st == "livre" else "beds:occupied", bid)
    await pipe.execute()
    yield
    await pool.disconnect()


mimetypes.add_type("font/woff2", ".woff2")
app = FastAPI(lifespan=lifespan)
@app.middleware("http")
async def sem_cache_estatico(request: Request, call_next):
    """Telas mudaram? O navegador revalida em vez de usar cópia velha."""
    resposta = await call_next(request)
    if request.url.path in ("/", "/operacao") or request.url.path.startswith("/static/"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


app.include_router(inspecao.criar(r, CHANNEL))
app.mount("/static", StaticFiles(directory="static"), name="static")


class PatientIn(BaseModel):
    name: str
    priority: int = Field(ge=1, le=5)  # 1 = emergência, 5 = não urgente
    paciente_id: int | None = None     # id do cadastro (Tema 1), quando o paciente já existe lá


@app.post("/patients")
async def register(p: PatientIn):
    pid = uuid.uuid4().hex[:12]
    now = int(time.time() * 1000)
    score = p.priority * 10**13 + now
    async with r.pipeline(transaction=True) as pipe:
        campos = {"name": p.name, "priority": p.priority, "status": "aguardando", "arrived_at": now}
        if p.paciente_id is not None:
            campos["paciente_id"] = p.paciente_id
        pipe.hset(f"patient:{pid}", mapping=campos)
        pipe.zadd(QUEUE, {pid: score})
        await pipe.execute()
    return {"id": pid}


@app.post("/triage/call-next")
async def call(room: str):
    res = await call_next(keys=[QUEUE, RECENT, CHANNEL], args=[room, int(time.time() * 1000)])
    if res is None:
        raise HTTPException(404, "Fila vazia")
    return json.loads(res)


@app.get("/triage/queue")
async def queue(limit: int = 20):
    ids = await r.zrange(QUEUE, 0, limit - 1)
    size = await r.zcard(QUEUE)
    pipe = r.pipeline()
    for i in ids:
        pipe.hgetall(f"patient:{i}")
    data = await pipe.execute()
    return {"size": size, "next": [{"id": i, **d} for i, d in zip(ids, data)]}


@app.get("/triage/called")
async def called():
    """Chamados nas últimas chamadas que ainda não foram internados nem receberam alta."""
    recentes = [json.loads(m) for m in await r.lrange(RECENT, 0, 19)]
    ids = list(dict.fromkeys(m["patient"] for m in recentes))
    pipe = r.pipeline()
    for i in ids:
        pipe.hgetall(f"patient:{i}")
    dados = await pipe.execute()
    return [{"id": i, **d} for i, d in zip(ids, dados) if d.get("status") == "chamado"]


@app.post("/beds/{bed_id}/allocate")
async def allocate(bed_id: str, patient_id: str):
    res = await allocate_bed(
        keys=[f"bed:{bed_id}", f"patient:{patient_id}", CHANNEL],
        args=[bed_id, patient_id, int(time.time() * 1000)])
    msgs = {0: "Leito já ocupado", -1: "Leito inexistente",
            -2: "Paciente inexistente", -3: "Paciente já possui leito"}
    if res != 1:
        raise HTTPException(409 if res == 0 else 404, msgs[res])
    return {"bed": bed_id, "patient": patient_id, "status": "ocupado"}


@app.post("/beds/{bed_id}/release")
async def release(bed_id: str):
    res = await release_bed(keys=[f"bed:{bed_id}", CHANNEL], args=[bed_id])
    if res != 1:
        raise HTTPException(409, "Leito já está livre ou não existe")
    return {"bed": bed_id, "status": "livre"}


@app.get("/beds")
async def beds():
    return {"free": await r.scard("beds:free"), "occupied": await r.scard("beds:occupied")}


@app.get("/beds/map")
async def beds_map():
    ids = [f"{i:03d}" for i in range(1, TOTAL_BEDS + 1)]
    pipe = r.pipeline()
    for b in ids:
        pipe.hgetall(f"bed:{b}")
    leitos = await pipe.execute()
    pipe = r.pipeline()
    for l in leitos:
        pipe.hget(f"patient:{l['patient']}", "name") if l.get("patient") else pipe.echo("")
    nomes = await pipe.execute()
    return [{"id": b, "status": l.get("status", "livre"), "patient": l.get("patient"), "name": n or None}
            for b, l, n in zip(ids, leitos, nomes)]


@app.get("/health")
async def health():
    await r.ping()
    return {"ok": True}


@app.websocket("/ws/painel")
async def painel(ws: WebSocket):
    await ws.accept()
    for m in reversed(await r.lrange(RECENT, 0, 9)):  # histórico recente ao conectar
        await ws.send_text(m)
    ps = r.pubsub()
    await ps.subscribe(CHANNEL)
    try:
        async for msg in ps.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await ps.close()


@app.get("/")
async def index():
    return FileResponse("static/painel.html")


@app.get("/operacao")
async def operacao():
    return FileResponse("static/operacao.html")
