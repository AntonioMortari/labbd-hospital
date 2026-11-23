import mimetypes
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pydantic import BaseModel

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
driver = GraphDatabase.driver(URI, auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "demonstracao123")))

@asynccontextmanager
async def lifespan(app):
    driver.verify_connectivity()
    for rotulo in ROTULOS.values():  # unicidade por tipo (o README original lista isso como próximo passo)
        executar(f"CREATE CONSTRAINT {rotulo.lower()}_id IF NOT EXISTS FOR (n:{rotulo}) REQUIRE n.id IS UNIQUE")
    yield
    driver.close()

app = FastAPI(title="Interações medicamentosas — demonstração", lifespan=lifespan)

class No(BaseModel):
    id: str
    nome: str

class Relacao(BaseModel):
    origem: str
    destino: str
    observacao: str = ""

# Rótulos e tipos são escolhidos em listas fixas; valores seguem parametrizados.
ROTULOS = {"pacientes": "Paciente", "medicamentos": "Medicamento", "patologias": "Patologia", "profissionais": "Profissional"}
RELACOES = {
    "prescricoes": ("Paciente", "USA", "Medicamento"),
    "alergias": ("Paciente", "ALERGICO_A", "Medicamento"),
    "diagnosticos": ("Paciente", "TEM", "Patologia"),
    "contraindicacoes": ("Medicamento", "CONTRAINDICADO_PARA", "Patologia"),
    "interacoes": ("Medicamento", "INTERAGE_COM", "Medicamento"),
    "atendimentos": ("Profissional", "ATENDE", "Paciente"),
    "contatos": ("Paciente", "CONTATO_COM", "Paciente"),
}

def executar(query, **params):
    with driver.session() as session:
        return [r.data() for r in session.run(query, **params)]

@app.post('/nos/{tipo}')
def criar_no(tipo: str, item: No):
    if tipo not in ROTULOS: raise HTTPException(404, 'Tipo desconhecido')
    label = ROTULOS[tipo]
    executar(f'MERGE (n:{label} {{id:$id}}) SET n.nome=$nome', **item.model_dump())
    return item

@app.post('/relacoes/{tipo}')
def criar_relacao(tipo: str, item: Relacao):
    if tipo not in RELACOES: raise HTTPException(404, 'Tipo desconhecido')
    a, rel, b = RELACOES[tipo]
    rows = executar(f'MATCH (a:{a} {{id:$origem}}), (b:{b} {{id:$destino}}) MERGE (a)-[r:{rel}]->(b) SET r.observacao=$observacao RETURN count(r) AS total', **item.model_dump())
    if not rows[0]['total']: raise HTTPException(404, 'Origem ou destino não encontrado')
    return {'ok': True}

@app.get('/pacientes/{paciente_id}/riscos')
def riscos(paciente_id: str):
    if not executar('MATCH (p:Paciente {id:$id}) RETURN p.id', id=paciente_id): raise HTTPException(404, 'Paciente não encontrado')
    query = '''MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)-[r:INTERAGE_COM]-(b:Medicamento)<-[:USA]-(p)
    WHERE a.id < b.id
    RETURN DISTINCT 'interacao' AS tipo, a.nome AS medicamento, b.nome AS relacionado, r.observacao AS observacao
    UNION
    MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)<-[r:ALERGICO_A]-(p)
    RETURN 'alergia' AS tipo, a.nome AS medicamento, a.nome AS relacionado, r.observacao AS observacao
    UNION
    MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)-[r:CONTRAINDICADO_PARA]->(d:Patologia)<-[:TEM]-(p)
    RETURN 'contraindicacao' AS tipo, a.nome AS medicamento, d.nome AS relacionado, r.observacao AS observacao'''
    return executar(query, id=paciente_id)

@app.get('/pacientes/{paciente_id}/contatos')
def contatos(paciente_id: str):
    return executar('MATCH (p:Paciente {id:$id})-[:CONTATO_COM]-(q:Paciente) RETURN DISTINCT q.id AS id, q.nome AS nome', id=paciente_id)

@app.post('/demonstracao')
def demonstracao():
    for tipo, id, nome in [('pacientes','p1','Paciente exemplo'),('pacientes','p2','Contato exemplo'),('medicamentos','m1','Medicamento A'),('medicamentos','m2','Medicamento B'),('patologias','d1','Condição exemplo'),('profissionais','pr1','Profissional exemplo')]: criar_no(tipo, No(id=id,nome=nome))
    for tipo, origem, destino in [('prescricoes','p1','m1'),('prescricoes','p1','m2'),('interacoes','m1','m2'),('alergias','p1','m1'),('diagnosticos','p1','d1'),('contraindicacoes','m2','d1'),('atendimentos','pr1','p1'),('contatos','p1','p2')]: criar_relacao(tipo, Relacao(origem=origem,destino=destino,observacao='Dado fictício'))
    return {'ok': True, 'paciente': 'p1'}


# ---------------------------------------------------------------------------------------------
# Integração ao sistema (acrescentado): /health, interface, listagem do grafo e análise com as consultas expostas.
# Os endpoints acima são os originais, sem mudança.
# ---------------------------------------------------------------------------------------------
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/static", StaticFiles(directory="static"), name="static")

CYPHER_INTERACAO = """MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)-[r:INTERAGE_COM]-(b:Medicamento)<-[:USA]-(p)
WHERE a.id < b.id
RETURN DISTINCT a.nome AS medicamento, b.nome AS relacionado, r.observacao AS observacao"""
CYPHER_ALERGIA = """MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)<-[r:ALERGICO_A]-(p)
RETURN a.nome AS medicamento, r.observacao AS observacao"""
CYPHER_CONTRA = """MATCH (p:Paciente {id:$id})-[:USA]->(a:Medicamento)-[r:CONTRAINDICADO_PARA]->(d:Patologia)<-[:TEM]-(p)
RETURN a.nome AS medicamento, d.nome AS patologia, r.observacao AS observacao"""
CYPHER_CONTATOS = """MATCH (p:Paciente {id:$id})-[:CONTATO_COM]-(q:Paciente)
RETURN DISTINCT q.id AS id, q.nome AS nome"""


@app.get("/", include_in_schema=False)
def pagina():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    driver.verify_connectivity()
    return {"ok": True}


@app.get("/grafo")
def grafo():
    """Todos os nós e arestas, para desenhar a rede."""
    nos = executar("MATCH (n) RETURN labels(n)[0] AS tipo, n.id AS id, n.nome AS nome ORDER BY tipo, nome")
    arestas = executar("MATCH (a)-[r]->(b) RETURN labels(a)[0] AS de_tipo, a.id AS de, type(r) AS relacao, "
                       "labels(b)[0] AS para_tipo, b.id AS para, r.observacao AS observacao")
    return {"nos": nos, "arestas": arestas}


def _medir(nome, cypher, **params):
    t0 = time.perf_counter()
    linhas = executar(cypher, **params)
    return {"nome": nome, "cypher": cypher, "tempo_ms": round((time.perf_counter() - t0) * 1000, 2), "linhas": len(linhas)}, linhas


@app.get("/pacientes/{paciente_id}/analise")
def analise(paciente_id: str):
    """Mesmas consultas de /riscos e /contatos, separadas por tipo e com o Cypher e o tempo de cada uma."""
    if not executar("MATCH (p:Paciente {id:$id}) RETURN p.id", id=paciente_id):
        raise HTTPException(404, "Paciente não encontrado")
    consultas, saida = [], {}
    for chave, nome, cy in (("interacoes", "Interação entre medicamentos", CYPHER_INTERACAO),
                            ("alergias", "Alergia a medicamento em uso", CYPHER_ALERGIA),
                            ("contraindicacoes", "Medicamento contraindicado para patologia", CYPHER_CONTRA),
                            ("contatos", "Contatos diretos", CYPHER_CONTATOS)):
        info, linhas = _medir(nome, cy, id=paciente_id)
        consultas.append(info)
        saida[chave] = linhas
    return {**saida, "consultas": consultas}


@app.delete("/grafo")
def limpar():
    executar("MATCH (n) DETACH DELETE n")
    return {"ok": True}


@app.post("/demonstracao/completa")
def demonstracao_completa():
    """Cenário maior para a apresentação. Dados fictícios: não são recomendações clínicas."""
    nos = [("pacientes", "1", "Ana Souza"), ("pacientes", "2", "Carlos Vencido"), ("pacientes", "3", "Beatriz Lima"),
           ("medicamentos", "m1", "Varfarina"), ("medicamentos", "m2", "Ácido acetilsalicílico"), ("medicamentos", "m3", "Ibuprofeno"),
           ("medicamentos", "m4", "Penicilina"), ("medicamentos", "m5", "Metformina"),
           ("patologias", "d1", "Úlcera gástrica"), ("patologias", "d2", "Insuficiência renal"),
           ("profissionais", "pr1", "Dra. Marina Costa"), ("profissionais", "pr2", "Dr. Paulo Mendes")]
    rels = [("prescricoes", "1", "m1"), ("prescricoes", "1", "m2"), ("prescricoes", "1", "m4"),
            ("prescricoes", "2", "m3"), ("prescricoes", "2", "m5"), ("prescricoes", "3", "m3"),
            ("interacoes", "m1", "m2"), ("interacoes", "m1", "m3"), ("interacoes", "m2", "m3"),
            ("alergias", "1", "m4"), ("diagnosticos", "1", "d1"), ("diagnosticos", "2", "d2"), ("diagnosticos", "3", "d1"),
            ("contraindicacoes", "m2", "d1"), ("contraindicacoes", "m3", "d1"), ("contraindicacoes", "m3", "d2"),
            ("atendimentos", "pr1", "1"), ("atendimentos", "pr1", "3"), ("atendimentos", "pr2", "2"),
            ("contatos", "1", "2"), ("contatos", "2", "3")]
    for tipo, id, nome in nos:
        criar_no(tipo, No(id=id, nome=nome))
    for tipo, origem, destino in rels:
        criar_relacao(tipo, Relacao(origem=origem, destino=destino, observacao="Dado fictício para demonstração"))
    return {"ok": True, "nos": len(nos), "relacoes": len(rels)}
