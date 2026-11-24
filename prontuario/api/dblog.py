"""O que o banco executou em cada requisição, para a tela "Bastidores".

Só liga quando o navegador pede (cabeçalho X-Log: 1): o resultado volta no cabeçalho X-DB-Log, comprimido e em base64.
"""
import base64
import json
import zlib
from contextvars import ContextVar

consultas: ContextVar[list | None] = ContextVar("consultas_db", default=None)
MAX_CONSULTAS, MAX_TEXTO, MAX_BYTES = 60, 4000, 24000


def iniciar() -> None:
    consultas.set([])


def _curto(v, n=240):
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return t if len(t) <= n else t[:n] + "…"


def registrar(tipo, texto, params=None, ms=None, linhas=None, erro=None, nota=None) -> None:
    lista = consultas.get()
    if lista is None or len(lista) >= MAX_CONSULTAS:
        return
    item = {"tipo": tipo, "texto": texto if len(texto) <= MAX_TEXTO else texto[:MAX_TEXTO] + "\n…"}
    if params:
        item["params"] = [_curto(p) for p in params] if isinstance(params, (list, tuple)) else {k: _curto(v) for k, v in params.items()}
    if ms is not None:
        item["ms"] = round(ms, 2)
    if linhas is not None:
        item["linhas"] = linhas
    if erro:
        item["erro"] = _curto(str(erro), 400)
    if nota:
        item["nota"] = nota
    lista.append(item)


def cabecalho() -> str | None:
    lista = consultas.get()
    if not lista:
        return None
    bruto = json.dumps(lista, ensure_ascii=False, default=str).encode()
    while len(bruto) > MAX_BYTES and len(lista) > 1:  # corta o excesso do fim, nunca o começo
        lista = lista[:-1]
        bruto = json.dumps(lista, ensure_ascii=False, default=str).encode()
    return base64.b64encode(zlib.compress(bruto, 6)).decode("ascii")

