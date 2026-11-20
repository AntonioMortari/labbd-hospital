"""Aba "Redis por dentro": mostra como os dados estão guardados no Redis. Somente leitura."""
import re
from fastapi import APIRouter

import scripts

router = APIRouter(prefix="/redis", tags=["redis"])
AMOSTRA = 8       # chaves de exemplo por grupo
MEMBROS = 60      # itens mostrados por chave


def _grupo(chave: str) -> str:
    """patient:ab12 e patient:cd34 viram o grupo patient:*; as demais chaves ficam sozinhas."""
    m = re.fullmatch(r"(patient|bed):[^:]+", chave)
    return f"{m.group(1)}:*" if m else chave


async def _conteudo(r, chave: str, tipo: str):
    if tipo == "hash":
        return await r.hgetall(chave)
    if tipo == "zset":
        return [{"membro": m, "pontuacao": s} for m, s in await r.zrange(chave, 0, MEMBROS - 1, withscores=True)]
    if tipo == "set":
        return sorted(await r.srandmember(chave, MEMBROS) or [])
    if tipo == "list":
        return await r.lrange(chave, 0, MEMBROS - 1)
    if tipo == "string":
        return await r.get(chave)
    return None


async def _tamanho(r, chave: str, tipo: str) -> int:
    f = {"hash": r.hlen, "zset": r.zcard, "set": r.scard, "list": r.llen, "string": r.strlen}.get(tipo)
    return await f(chave) if f else 0


def criar(r, canal: str):
    @router.get("/estruturas")
    async def estruturas():
        grupos: dict[str, list[str]] = {}
        async for chave in r.scan_iter(count=1000):
            grupos.setdefault(_grupo(chave), []).append(chave)
        saida = []
        for nome, chaves in sorted(grupos.items()):
            chaves.sort()
            tipo = await r.type(chaves[0])
            amostra = []
            for c in chaves[:AMOSTRA]:
                ttl = await r.ttl(c)
                amostra.append({"chave": c, "tamanho": await _tamanho(r, c, tipo), "ttl": None if ttl < 0 else ttl,
                                "conteudo": await _conteudo(r, c, tipo)})
            saida.append({"grupo": nome, "tipo": tipo, "chaves": len(chaves), "amostra": amostra})
        info = await r.info()
        inscritos = (await r.pubsub_numsub(canal))[0][1]
        return {
            "grupos": saida,
            "canal": {"nome": canal, "inscritos": inscritos},
            "servidor": {"versao": info.get("redis_version"), "memoria": info.get("used_memory_human"),
                         "clientes": info.get("connected_clients"), "ops_por_s": info.get("instantaneous_ops_per_sec"),
                         "comandos": info.get("total_commands_processed")},
        }

    @router.get("/scripts")
    async def lista_scripts():
        return [{"nome": n, "codigo": getattr(scripts, n).strip()} for n in ("CALL_NEXT", "ALLOCATE_BED", "RELEASE_BED")]

    return router
