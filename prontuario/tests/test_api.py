import os
import random
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

BASE = os.getenv("BASE_URL", "http://localhost:8084")
AUD = {"responsavel_id": 1, "justificativa": "Teste automatizado"}


@pytest.fixture
def api():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c


@pytest.fixture
def paciente(api):
    pid = random.randint(500_000, 9_000_000)
    r = api.post("/prontuarios", json={"paciente_id": pid, "historico_clinico": {"alergias": ["Teste"]}})
    assert r.status_code == 201, r.text
    return pid


def test_backup_restaurado(api):
    d = api.get("/prontuarios/1001").json()
    assert d["versao"] >= 6 and len(d["exames"]) >= 2
    assert len(api.get("/prontuarios/1001/versoes").json()["alteracoes"]) >= 5


def test_prontuario_novo_comeca_na_versao_1_e_nao_duplica(api, paciente):
    assert api.get(f"/prontuarios/{paciente}").json()["versao"] == 1
    assert api.post("/prontuarios", json={"paciente_id": paciente}).status_code == 409


def test_prontuario_inexistente(api):
    assert api.get("/prontuarios/999999999").status_code == 404


def test_alteracao_guarda_versao_anterior_com_auditoria(api, paciente):
    r = api.post(f"/prontuarios/{paciente}/evolucoes", json={**AUD, "descricao": "Primeira evolução"})
    assert r.status_code == 201 and r.json()["versao"] == 2
    v = api.get(f"/prontuarios/{paciente}/versoes").json()
    assert v["versao_atual"] == 2 and len(v["alteracoes"]) == 1
    a = v["alteracoes"][0]
    assert (a["de_versao"], a["para_versao"]) == (1, 2)
    assert a["auditoria"]["justificativa"] == "Teste automatizado" and a["auditoria"]["responsavel_id"] == 1
    assert api.get(f"/prontuarios/{paciente}/versoes/1").json()["evolucoes"] == []


def test_correcao_mostra_o_que_mudou(api, paciente):
    api.post(f"/prontuarios/{paciente}/evolucoes", json={**AUD, "descricao": "Febre de 38 graus"})
    api.put(f"/prontuarios/{paciente}/evolucoes/0", json={**AUD, "descricao": "Febre de 39 graus"})
    mud = api.get(f"/prontuarios/{paciente}/versoes").json()["alteracoes"][1]["mudancas"]
    assert mud == [{"caminho": "evolucoes[0].descricao", "antes": "Febre de 38 graus", "depois": "Febre de 39 graus"}]


def test_sem_justificativa_nao_altera(api, paciente):
    r = api.post(f"/prontuarios/{paciente}/evolucoes", json={"responsavel_id": 1, "justificativa": "ok", "descricao": "Texto"})
    assert r.status_code == 422
    assert api.get(f"/prontuarios/{paciente}").json()["versao"] == 1


def test_exames_aceitam_estruturas_diferentes(api, paciente):
    api.post(f"/prontuarios/{paciente}/exames", json={**AUD, "tipo": "Glicemia", "resultado": {"glicose": 92, "unidade": "mg/dL"}})
    api.post(f"/prontuarios/{paciente}/exames", json={**AUD, "tipo": "Hemograma", "resultado": {"hemoglobina": {"valor": 14.2, "unidade": "g/dL"}}})
    ex = api.get(f"/prontuarios/{paciente}").json()["exames"]
    assert ex[0]["resultado"] != ex[1]["resultado"] and ex[1]["resultado"]["hemoglobina"]["valor"] == 14.2
    assert api.post(f"/prontuarios/{paciente}/exames", json={**AUD, "tipo": "Vazio", "resultado": {}}).status_code == 422


def test_evolucao_inexistente(api, paciente):
    assert api.put(f"/prontuarios/{paciente}/evolucoes/5", json={**AUD, "descricao": "Texto"}).status_code == 404
    assert api.get(f"/prontuarios/{paciente}").json()["versao"] == 1  # a tentativa recusada não cria versão


def test_alteracoes_simultaneas_nao_perdem_historico(api, paciente):
    def alterar(i):
        with httpx.Client(base_url=BASE, timeout=10) as c:
            return c.post(f"/prontuarios/{paciente}/evolucoes", json={**AUD, "descricao": f"Evolução {i}"}).status_code
    with ThreadPoolExecutor(8) as ex:
        codigos = list(ex.map(alterar, range(8)))
    assert set(codigos) <= {201, 409} and codigos.count(201) >= 1
    d = api.get(f"/prontuarios/{paciente}").json()
    # cada alteração aceita gerou exatamente uma versão nova e uma cópia no histórico
    assert d["versao"] == 1 + codigos.count(201)
    assert len(api.get(f"/prontuarios/{paciente}/versoes").json()["alteracoes"]) == codigos.count(201)
    assert len(d["evolucoes"]) == codigos.count(201)


def test_colecoes(api):
    nomes = {c["nome"] for c in api.get("/colecoes").json()["colecoes"]}
    assert {"prontuarios", "historico_versoes"} <= nomes
