"""Tema 4: Prontuário Eletrônico do Paciente (MongoDB).

Modelo entregue pelo Gustavo: um documento por paciente em `prontuarios` (com evoluções, exames de formato variável e
prescrições embutidos) e, em `historico_versoes`, a cópia de cada versão anterior com a auditoria da alteração.
"""
import copy
import mimetypes
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

mimetypes.add_type("font/woff2", ".woff2")
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True, serverSelectionTimeoutMS=5000)
db = client[os.getenv("MONGO_DB", "prontuario_medico")]
prontuarios, historico = db["prontuarios"], db["historico_versoes"]
SECOES = ("historico_clinico", "evolucoes", "exames", "prescricoes")


@asynccontextmanager
async def lifespan(app):
    client.admin.command("ping")
    prontuarios.create_index([("paciente_id", ASCENDING)], unique=True, name="paciente_unico")
    # uma única cópia por versão: é isso que impede duas alterações simultâneas de gravarem a mesma versão
    historico.create_index([("prontuario_id", ASCENDING), ("numero_versao", ASCENDING)], unique=True, name="versao_unica")
    yield
    client.close()


app = FastAPI(title="Tema 4 — Prontuário Eletrônico (MongoDB)", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def agora():
    return datetime.now(timezone.utc)


def ser(o):
    """Converte o que o Mongo devolve (ObjectId, datas) em JSON."""
    if isinstance(o, ObjectId):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: ser(v) for k, v in o.items()}
    if isinstance(o, list):
        return [ser(v) for v in o]
    return o


# ---------------------------------------------------------------- modelos
class Auditoria(BaseModel):
    responsavel_id: int = Field(gt=0, description="Médico que está alterando")
    justificativa: str = Field(min_length=5, max_length=500)

    @field_validator("justificativa")
    @classmethod
    def _sem_espacos(cls, v):
        v = v.strip()
        if len(v) < 5:
            raise ValueError("A justificativa precisa ter pelo menos 5 caracteres")
        return v


class HistoricoClinico(BaseModel):
    alergias: list[str] = []
    doencas_cronicas: list[str] = []
    antecedentes: str = ""


class NovoProntuario(BaseModel):
    paciente_id: int = Field(gt=0)
    historico_clinico: HistoricoClinico = HistoricoClinico()


class AlteraHistorico(Auditoria, HistoricoClinico):
    pass


class NovaEvolucao(Auditoria):
    descricao: str = Field(min_length=3)


class EditaEvolucao(Auditoria):
    descricao: str = Field(min_length=3)


class NovoExame(Auditoria):
    tipo: str = Field(min_length=2)
    laboratorio: str = ""
    resultado: dict = Field(min_length=1, description="Estrutura livre: cada tipo de exame tem os seus campos")
    laudo: str = ""


class NovaPrescricao(Auditoria):
    medicamento: str = Field(min_length=2)
    dosagem: str = ""
    frequencia: str = ""
    duracao: str = ""
    observacoes: str = ""


# ---------------------------------------------------------------- versionamento
def obter(paciente_id: int) -> dict:
    doc = prontuarios.find_one({"paciente_id": paciente_id})
    if not doc:
        raise HTTPException(404, "Prontuário não encontrado")
    return doc


def alterar(paciente_id: int, aud: Auditoria, mutar) -> dict:
    """Grava a versão atual em historico_versoes (com a auditoria) e só então aplica a mudança.

    Controle otimista: a cópia da versão N tem índice único, e o update só vale se a versão ainda for N.
    Se outra alteração chegou antes, esta é recusada com 409 em vez de sobrescrever em silêncio.
    """
    atual = obter(paciente_id)
    novo = copy.deepcopy(atual)
    mutar(novo)
    try:
        historico.insert_one({
            "prontuario_id": atual["_id"], "numero_versao": atual["versao"], "dados": atual,
            "auditoria": {"responsavel_id": aud.responsavel_id, "data_alteracao": agora(), "justificativa": aud.justificativa},
        })
    except DuplicateKeyError:
        raise HTTPException(409, "Outra alteração foi gravada ao mesmo tempo. Recarregue o prontuário e tente de novo.")
    r = prontuarios.update_one({"_id": atual["_id"], "versao": atual["versao"]},
                               {"$set": {s: novo[s] for s in SECOES}, "$inc": {"versao": 1}})
    if r.modified_count != 1:
        historico.delete_one({"prontuario_id": atual["_id"], "numero_versao": atual["versao"]})
        raise HTTPException(409, "O prontuário mudou durante a gravação. Recarregue e tente de novo.")
    return prontuarios.find_one({"_id": atual["_id"]})


def diferencas(a, b, caminho=""):
    """Lista o que mudou entre duas versões: [{caminho, antes, depois}]."""
    saida = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if not caminho and k in ("_id", "versao"):
                continue
            saida += diferencas(a.get(k), b.get(k), f"{caminho}.{k}" if caminho else k)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            saida += diferencas(a[i] if i < len(a) else None, b[i] if i < len(b) else None, f"{caminho}[{i}]")
    elif a != b:
        saida.append({"caminho": caminho, "antes": ser(a), "depois": ser(b)})
    return saida


# ---------------------------------------------------------------- rotas
@app.get("/", include_in_schema=False)
def pagina():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    client.admin.command("ping")
    return {"ok": True}


@app.get("/prontuarios")
def listar():
    saida = []
    for d in prontuarios.find().sort("paciente_id", ASCENDING):
        saida.append({"paciente_id": d["paciente_id"], "versao": d["versao"], "criado_em": ser(d["criado_em"]),
                      "alergias": d["historico_clinico"].get("alergias", []),
                      "evolucoes": len(d["evolucoes"]), "exames": len(d["exames"]), "prescricoes": len(d["prescricoes"])})
    return saida


@app.get("/prontuarios/{paciente_id}")
def ver(paciente_id: int):
    return ser(obter(paciente_id))


@app.post("/prontuarios", status_code=201)
def criar(p: NovoProntuario):
    doc = {"paciente_id": p.paciente_id, "versao": 1, "criado_em": agora(), "historico_clinico": p.historico_clinico.model_dump(),
           "evolucoes": [], "exames": [], "prescricoes": []}
    try:
        prontuarios.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Este paciente já tem prontuário")
    return ser(doc)


@app.put("/prontuarios/{paciente_id}/historico-clinico")
def alterar_historico(paciente_id: int, b: AlteraHistorico):
    def mutar(d):
        d["historico_clinico"] = {"alergias": b.alergias, "doencas_cronicas": b.doencas_cronicas, "antecedentes": b.antecedentes}
    return ser(alterar(paciente_id, b, mutar))


@app.post("/prontuarios/{paciente_id}/evolucoes", status_code=201)
def nova_evolucao(paciente_id: int, b: NovaEvolucao):
    return ser(alterar(paciente_id, b, lambda d: d["evolucoes"].append(
        {"data": agora(), "medico_id": b.responsavel_id, "descricao": b.descricao.strip()})))


@app.put("/prontuarios/{paciente_id}/evolucoes/{indice}")
def corrigir_evolucao(paciente_id: int, indice: int, b: EditaEvolucao):
    def mutar(d):
        if not 0 <= indice < len(d["evolucoes"]):
            raise HTTPException(404, "Evolução inexistente")
        d["evolucoes"][indice]["descricao"] = b.descricao.strip()
    return ser(alterar(paciente_id, b, mutar))


@app.post("/prontuarios/{paciente_id}/exames", status_code=201)
def novo_exame(paciente_id: int, b: NovoExame):
    return ser(alterar(paciente_id, b, lambda d: d["exames"].append(
        {"tipo": b.tipo.strip(), "data": agora(), "laboratorio": b.laboratorio, "resultado": b.resultado, "laudo": b.laudo})))


@app.post("/prontuarios/{paciente_id}/prescricoes", status_code=201)
def nova_prescricao(paciente_id: int, b: NovaPrescricao):
    return ser(alterar(paciente_id, b, lambda d: d["prescricoes"].append(
        {"data": agora(), "medico_id": b.responsavel_id, "medicamento": b.medicamento.strip(), "dosagem": b.dosagem,
         "frequencia": b.frequencia, "duracao": b.duracao, "observacoes": b.observacoes})))


@app.get("/prontuarios/{paciente_id}/versoes")
def versoes(paciente_id: int):
    atual = obter(paciente_id)
    snaps = list(historico.find({"prontuario_id": atual["_id"]}).sort("numero_versao", ASCENDING))
    alteracoes = []
    for i, s in enumerate(snaps):
        seguinte = snaps[i + 1]["dados"] if i + 1 < len(snaps) else atual
        alteracoes.append({"de_versao": s["numero_versao"], "para_versao": s["numero_versao"] + 1,
                           "auditoria": ser(s["auditoria"]), "mudancas": diferencas(s["dados"], seguinte)})
    return {"paciente_id": paciente_id, "versao_atual": atual["versao"], "criado_em": ser(atual["criado_em"]), "alteracoes": alteracoes}


@app.get("/prontuarios/{paciente_id}/versoes/{numero}")
def ver_versao(paciente_id: int, numero: int):
    atual = obter(paciente_id)
    if numero == atual["versao"]:
        return ser(atual)
    s = historico.find_one({"prontuario_id": atual["_id"], "numero_versao": numero})
    if not s:
        raise HTTPException(404, "Versão inexistente")
    return ser(s["dados"])


@app.get("/colecoes")
def colecoes():
    """Para a tela "MongoDB por dentro": coleções, índices e um documento de exemplo."""
    saida = []
    for nome in sorted(db.list_collection_names()):
        c = db[nome]
        ex = c.find_one(sort=[("_id", DESCENDING)])
        saida.append({"nome": nome, "documentos": c.estimated_document_count(),
                      "indices": [{"nome": n, "chave": list(i["key"]), "unico": bool(i.get("unique"))} for n, i in c.index_information().items()],
                      "exemplo": ser(ex) if ex else None})
    info = client.server_info()
    return {"banco": db.name, "versao_mongo": info.get("version"), "colecoes": saida}


@app.post("/demonstracao")
def demonstracao():
    """Prontuários de exemplo para os pacientes 1 e 2 do cadastro (dados fictícios). Não mexe no que já existe."""
    criados = []
    if not prontuarios.find_one({"paciente_id": 1}):
        criar(NovoProntuario(paciente_id=1, historico_clinico=HistoricoClinico(
            alergias=["Penicilina"], doencas_cronicas=["Hipertensão"], antecedentes="Histórico familiar de diabetes.")))
        nova_evolucao(1, NovaEvolucao(responsavel_id=1, justificativa="Primeira consulta", descricao="Queixa de cefaleia há 3 dias. PA 150x95."))
        novo_exame(1, NovoExame(responsavel_id=1, justificativa="Exame solicitado na consulta", tipo="Glicemia em jejum",
                                laboratorio="Laboratório exemplo", resultado={"glicose": 98, "unidade": "mg/dL"}, laudo="Dentro do esperado."))
        corrigir_evolucao(1, 0, EditaEvolucao(responsavel_id=1, justificativa="Correção da pressão registrada",
                                               descricao="Queixa de cefaleia há 3 dias. PA 160x100."))
        criados.append(1)
    if not prontuarios.find_one({"paciente_id": 2}):
        criar(NovoProntuario(paciente_id=2, historico_clinico=HistoricoClinico(doencas_cronicas=["Asma"], antecedentes="")))
        nova_evolucao(2, NovaEvolucao(responsavel_id=2, justificativa="Retorno de rotina", descricao="Sem queixas. Mantém acompanhamento."))
        criados.append(2)
    return {"ok": True, "criados": criados}
