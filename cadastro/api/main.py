"""Tema 1 — API de cadastro, agendamento e faturamento.

A API é fina de propósito: as regras (integridade, conflito de horário, auditoria,
faturamento) são garantidas pelo PostgreSQL. Aqui só há SQL escrito à mão.
"""
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import catalogo
import db
import dblog

mimetypes.add_type("font/woff2", ".woff2")  # a imagem slim do Python não conhece .woff2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/hospital")


@asynccontextmanager
async def lifespan(app):
    await db.init_pool(DATABASE_URL)
    yield
    await db.close_pool()


app = FastAPI(title="Tema 1 — Cadastro e Agendamentos", lifespan=lifespan)
@app.middleware("http")
async def sem_cache_estatico(request: Request, call_next):
    """Interface mudou? O navegador revalida em vez de usar uma cópia velha (evita abas que não abrem)."""
    resposta = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


app.include_router(catalogo.router)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.middleware("http")
async def log_do_banco(request, call_next):
    """Se o navegador pediu (X-Log: 1), devolve o que o banco executou nesta requisição."""
    if request.headers.get("x-log") != "1":
        return await call_next(request)
    dblog.iniciar()
    resposta = await call_next(request)
    h = dblog.cabecalho()
    if h:
        resposta.headers["X-DB-Log"] = h
    return resposta

# Interface e API de OUTROS módulos (grafo.localhost, triagem.localhost...) chamam esta API pelo navegador.
# Só origens em localhost, sem credenciais: nenhum site externo ganha acesso.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://([a-z0-9-]+\.)*localhost(:\d+)?$",
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-Usuario"],
)


@app.exception_handler(asyncpg.PostgresError)
@app.exception_handler(asyncpg.DataError)
async def erro_banco(request: Request, e: Exception):
    http = db.erro_http(e)
    # sqlstate e regra vêm do próprio Postgres: a interface mostra qual regra recusou a operação
    return JSONResponse(status_code=http.status_code, content={
        "detail": http.detail,
        "sqlstate": getattr(e, "sqlstate", None),
        "regra": getattr(e, "constraint_name", None),
    })


def linha(r) -> dict:
    return dict(r) if r is not None else None


def linhas(rs) -> list[dict]:
    return [dict(r) for r in rs]


# ---------------------------------------------------------------- página de demo
@app.get("/", include_in_schema=False)
async def pagina():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------- saúde
@app.get("/health")
async def health():
    await db.pool.fetchval("SELECT 1")
    return {"ok": True}


# ---------------------------------------------------------------- pacientes
class PacienteIn(BaseModel):
    nome: str
    cpf: str
    data_nascimento: date
    telefone: str | None = None
    plano_id: int | None = None
    carteirinha: str | None = None
    validade_carteirinha: date | None = None


CAMPOS_PACIENTE = "id, nome, cpf, data_nascimento, telefone, plano_id, carteirinha, validade_carteirinha"


@app.get("/pacientes")
async def listar_pacientes(nome: str | None = None):
    rs = await db.pool.fetch(
        f"SELECT {CAMPOS_PACIENTE} FROM paciente WHERE $1::text IS NULL OR nome ILIKE '%' || $1 || '%' ORDER BY id",
        nome)
    return linhas(rs)


@app.get("/pacientes/{pid}")
async def obter_paciente(pid: int):
    r = await db.pool.fetchrow(f"SELECT {CAMPOS_PACIENTE} FROM paciente WHERE id = $1", pid)
    if r is None:
        raise HTTPException(404, "Paciente não encontrado")
    return linha(r)


@app.post("/pacientes", status_code=201)
async def criar_paciente(p: PacienteIn, x_usuario: str = Header("api")):
    async with db.tx(x_usuario) as conn:
        r = await conn.fetchrow(
            f"""INSERT INTO paciente (nome, cpf, data_nascimento, telefone, plano_id, carteirinha, validade_carteirinha)
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING {CAMPOS_PACIENTE}""",
            p.nome, p.cpf, p.data_nascimento, p.telefone, p.plano_id, p.carteirinha, p.validade_carteirinha)
    return linha(r)


@app.put("/pacientes/{pid}")
async def alterar_paciente(pid: int, p: PacienteIn, x_usuario: str = Header("api")):
    async with db.tx(x_usuario) as conn:
        r = await conn.fetchrow(
            f"""UPDATE paciente SET nome = $2, cpf = $3, data_nascimento = $4, telefone = $5,
                       plano_id = $6, carteirinha = $7, validade_carteirinha = $8
                 WHERE id = $1 RETURNING {CAMPOS_PACIENTE}""",
            pid, p.nome, p.cpf, p.data_nascimento, p.telefone, p.plano_id, p.carteirinha, p.validade_carteirinha)
    if r is None:
        raise HTTPException(404, "Paciente não encontrado")
    return linha(r)


# ---------------------------------------------------------------- cadastros de apoio
@app.get("/medicos")
async def listar_medicos():
    rs = await db.pool.fetch(
        """SELECT m.id, m.nome, m.crm, m.especialidade_id, e.nome AS especialidade
             FROM medico m JOIN especialidade e ON e.id = m.especialidade_id ORDER BY m.id""")
    return linhas(rs)


@app.get("/especialidades")
async def listar_especialidades():
    return linhas(await db.pool.fetch("SELECT id, nome, valor_consulta FROM especialidade ORDER BY id"))


@app.get("/convenios")
async def listar_convenios():
    rs = await db.pool.fetch(
        """SELECT c.id, c.nome, c.cnpj,
                  coalesce(json_agg(json_build_object('id', p.id, 'nome', p.nome, 'cobertura_pct', p.cobertura_pct)
                                    ORDER BY p.id) FILTER (WHERE p.id IS NOT NULL), '[]') AS planos
             FROM convenio c LEFT JOIN plano p ON p.convenio_id = c.id
            GROUP BY c.id ORDER BY c.id""")
    return linhas(rs)


# ---------------------------------------------------------------- agendamentos
class AgendamentoIn(BaseModel):
    paciente_id: int
    medico_id: int
    tipo: str = "consulta"
    inicio: str  # ISO 8601; sem fuso = horário de São Paulo (fuso do banco)
    fim: str
    valor_cirurgia: Decimal | None = None


CAMPOS_AGENDAMENTO = """a.id, a.paciente_id, a.medico_id, a.tipo, a.status, a.valor_cirurgia,
    to_char(lower(a.periodo), 'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM') AS inicio,
    to_char(upper(a.periodo), 'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM') AS fim"""


@app.post("/agendamentos", status_code=201)
async def agendar(a: AgendamentoIn, x_usuario: str = Header("api")):
    async with db.tx(x_usuario) as conn:
        # O banco recusa sobreposição (exclusion constraint) mesmo com pedidos simultâneos.
        novo = await conn.fetchval(
            """INSERT INTO agendamento (paciente_id, medico_id, tipo, periodo, valor_cirurgia)
               VALUES ($1, $2, $3, tstzrange($4::text::timestamptz, $5::text::timestamptz, '[)'), $6)
               RETURNING id""",
            a.paciente_id, a.medico_id, a.tipo, a.inicio, a.fim, a.valor_cirurgia)
        r = await conn.fetchrow(f"SELECT {CAMPOS_AGENDAMENTO} FROM agendamento a WHERE a.id = $1", novo)
    return linha(r)


@app.get("/agendamentos")
async def listar_agendamentos(medico_id: int | None = None, paciente_id: int | None = None,
                              data: date | None = None):
    rs = await db.pool.fetch(
        f"""SELECT {CAMPOS_AGENDAMENTO}, p.nome AS paciente, m.nome AS medico
              FROM agendamento a
              JOIN paciente p ON p.id = a.paciente_id
              JOIN medico m ON m.id = a.medico_id
             WHERE ($1::int IS NULL OR a.medico_id = $1)
               AND ($2::int IS NULL OR a.paciente_id = $2)
               AND ($3::date IS NULL OR lower(a.periodo)::date = $3)
             ORDER BY lower(a.periodo)""",
        medico_id, paciente_id, data)
    return linhas(rs)


@app.post("/agendamentos/{aid}/cancelar")
async def cancelar(aid: int, x_usuario: str = Header("api")):
    async with db.tx(x_usuario) as conn:
        r = await conn.fetchrow(
            "UPDATE agendamento SET status = 'cancelado' WHERE id = $1 AND status = 'agendado' RETURNING id", aid)
        if r is None:
            status = await conn.fetchval("SELECT status FROM agendamento WHERE id = $1", aid)
            if status is None:
                raise HTTPException(404, "Agendamento não encontrado")
            raise HTTPException(422, f"Agendamento não pode ser cancelado (status: {status})")
        r = await conn.fetchrow(f"SELECT {CAMPOS_AGENDAMENTO} FROM agendamento a WHERE a.id = $1", aid)
    return linha(r)


@app.post("/agendamentos/{aid}/realizar", status_code=201)
async def realizar(aid: int, x_usuario: str = Header("api")):
    async with db.tx(x_usuario) as conn:
        # Procedure transacional: fatura + status juntos, ou nada.
        fatura_id = await conn.fetchval("CALL realizar_atendimento($1, NULL)", aid)
        r = await conn.fetchrow("SELECT * FROM fatura WHERE id = $1", fatura_id)
    return linha(r)


# ---------------------------------------------------------------- faturas e auditoria
@app.get("/faturas")
async def listar_faturas(limit: int = 50):
    rs = await db.pool.fetch(
        """SELECT f.*, p.nome AS paciente, a.tipo
             FROM fatura f
             JOIN agendamento a ON a.id = f.agendamento_id
             JOIN paciente p ON p.id = a.paciente_id
            ORDER BY f.id DESC LIMIT $1""", limit)
    return linhas(rs)


@app.get("/auditoria")
async def listar_auditoria(limit: int = 50):
    rs = await db.pool.fetch("SELECT * FROM auditoria ORDER BY id DESC LIMIT $1", limit)
    return linhas(rs)
