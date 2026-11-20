"""Aba "Banco": estrutura do schema lida do próprio PostgreSQL (somente leitura).

Nada aqui aceita SQL do usuário: os nomes de tabela vêm do catálogo e a rota de dados só abre tabelas que ele lista.
"""
import re
from fastapi import APIRouter, HTTPException, Query

import db

router = APIRouter(prefix="/banco", tags=["banco"])

TIPO_RESTRICAO = {"p": "PRIMARY KEY", "f": "FOREIGN KEY", "u": "UNIQUE", "c": "CHECK", "x": "EXCLUDE"}

SQL_TABELAS = """
SELECT c.oid, c.relname AS nome
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r'
 ORDER BY c.relname"""

SQL_COLUNAS = """
SELECT a.attrelid AS rel, a.attname AS nome, format_type(a.atttypid, a.atttypmod) AS tipo,
       a.attnotnull AS obrigatoria, pg_get_expr(d.adbin, d.adrelid) AS padrao
  FROM pg_attribute a
  LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
 WHERE a.attrelid = ANY($1::oid[]) AND a.attnum > 0 AND NOT a.attisdropped
 ORDER BY a.attrelid, a.attnum"""

SQL_RESTRICOES = """
SELECT con.conrelid AS rel, con.conname AS nome, con.contype::text AS tipo,
       pg_get_constraintdef(con.oid) AS definicao,
       ARRAY(SELECT a.attname FROM unnest(con.conkey) k JOIN pg_attribute a
              ON a.attrelid = con.conrelid AND a.attnum = k) AS colunas,
       ref.relname AS tabela_ref,
       ARRAY(SELECT a.attname FROM unnest(con.confkey) k JOIN pg_attribute a
              ON a.attrelid = con.confrelid AND a.attnum = k) AS colunas_ref
  FROM pg_constraint con LEFT JOIN pg_class ref ON ref.oid = con.confrelid
 WHERE con.conrelid = ANY($1::oid[])
 ORDER BY con.conrelid, con.contype, con.conname"""

SQL_TRIGGERS = """
SELECT t.tgrelid AS rel, t.tgname AS nome, pg_get_triggerdef(t.oid) AS definicao, p.proname AS funcao
  FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
 WHERE NOT t.tgisinternal AND t.tgrelid = ANY($1::oid[])
 ORDER BY t.tgrelid, t.tgname"""

SQL_ROTINAS = """
SELECT p.proname AS nome,
       CASE WHEN p.prokind = 'p' THEN 'procedure' WHEN p.prorettype = 'trigger'::regtype THEN 'trigger' ELSE 'função' END AS tipo,
       pg_get_function_arguments(p.oid) AS argumentos,
       pg_get_functiondef(p.oid) AS definicao
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
   AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')  -- sem funções de extensões (btree_gist)
 ORDER BY (p.prokind = 'p') DESC, p.proname"""


def _momento_evento(definicao: str) -> tuple[str, str]:
    m = re.search(r"\b(BEFORE|AFTER|INSTEAD OF)\s+(.+?)\s+ON\b", definicao)
    return (m.group(1), m.group(2)) if m else ("", "")


@router.get("/estrutura")
async def estrutura():
    tabelas = await db.pool.fetch(SQL_TABELAS)
    oids = [t["oid"] for t in tabelas]
    colunas = await db.pool.fetch(SQL_COLUNAS, oids)
    restricoes = await db.pool.fetch(SQL_RESTRICOES, oids)
    triggers = await db.pool.fetch(SQL_TRIGGERS, oids)
    rotinas = await db.pool.fetch(SQL_ROTINAS)

    saida, relacoes = [], []
    for t in tabelas:
        rel, nome = t["oid"], t["nome"]
        rs = [r for r in restricoes if r["rel"] == rel]
        pk = {c for r in rs if r["tipo"] == "p" for c in r["colunas"]}
        unicas = {c for r in rs if r["tipo"] == "u" and len(r["colunas"]) == 1 for c in r["colunas"]}
        fks = {c: (r["tabela_ref"], r["colunas_ref"][i]) for r in rs if r["tipo"] == "f"
               for i, c in enumerate(r["colunas"])}
        for r in rs:
            if r["tipo"] == "f":
                relacoes.append({"de": nome, "colunas": list(r["colunas"]), "para": r["tabela_ref"],
                                 "colunas_ref": list(r["colunas_ref"]), "nome": r["nome"]})
        # linhas: contagem exata; o nome vem do catálogo, então é seguro citá-lo
        n = await db.pool.fetchval(f'SELECT count(*) FROM public."{nome}"')
        saida.append({
            "nome": nome, "linhas": n,
            "colunas": [{
                "nome": c["nome"], "tipo": c["tipo"], "obrigatoria": c["obrigatoria"], "padrao": c["padrao"],
                "pk": c["nome"] in pk, "unica": c["nome"] in unicas,
                "fk": {"tabela": fks[c["nome"]][0], "coluna": fks[c["nome"]][1]} if c["nome"] in fks else None,
            } for c in colunas if c["rel"] == rel],
            "restricoes": [{"nome": r["nome"], "tipo": TIPO_RESTRICAO.get(r["tipo"], r["tipo"]),
                            "definicao": r["definicao"]} for r in rs],
            "triggers": [{"nome": g["nome"], "funcao": g["funcao"], "definicao": g["definicao"],
                          **dict(zip(("momento", "evento"), _momento_evento(g["definicao"])))}
                         for g in triggers if g["rel"] == rel],
        })
    return {"tabelas": saida, "relacoes": relacoes, "rotinas": [dict(r) for r in rotinas]}


@router.get("/tabelas/{nome}/dados")
async def dados(nome: str, limit: int = Query(50, ge=1, le=200)):
    nomes = {t["nome"] for t in await db.pool.fetch(SQL_TABELAS)}
    if nome not in nomes:
        raise HTTPException(404, "Tabela inexistente")
    # to_jsonb transforma qualquer tipo (intervalos, datas, numeric) em JSON; a ordenação por 1 usa a primeira coluna
    rs = await db.pool.fetch(f'SELECT to_jsonb(t) AS linha FROM public."{nome}" t ORDER BY 1 DESC LIMIT $1', limit)
    return {"tabela": nome, "linhas": [r["linha"] for r in rs]}
