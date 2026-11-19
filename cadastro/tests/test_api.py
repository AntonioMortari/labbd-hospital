import random

import httpx
import pytest

from conftest import BASE_URL, cpf_unico


@pytest.fixture
def api():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


def _horario():
    """Um dia aleatório bem no futuro, para não colidir com execuções anteriores."""
    ano, mes, dia = random.randint(2031, 2099), random.randint(1, 12), random.randint(1, 28)
    hora = random.randint(8, 17)
    base = f"{ano}-{mes:02d}-{dia:02d}"
    return f"{base}T{hora:02d}:00:00", f"{base}T{hora:02d}:30:00", base, hora


def _paciente(api, **extra):
    body = {"nome": "Paciente API", "cpf": cpf_unico(), "data_nascimento": "1990-01-01", **extra}
    r = api.post("/pacientes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _medico_id(api):
    return api.get("/medicos").json()[0]["id"]


def _agendar(api, paciente_id, medico_id, inicio, fim, **extra):
    return api.post("/agendamentos", json={"paciente_id": paciente_id, "medico_id": medico_id,
                                           "tipo": "consulta", "inicio": inicio, "fim": fim, **extra})


def test_health(api):
    assert api.get("/health").status_code == 200


def test_cria_e_lista_paciente(api):
    pac = _paciente(api, telefone="(19) 90000-0000")
    r = api.get(f"/pacientes/{pac['id']}")
    assert r.status_code == 200
    assert r.json()["cpf"] == pac["cpf"]


def test_paciente_inexistente_404(api):
    assert api.get("/pacientes/999999").status_code == 404


def test_cpf_duplicado_409(api):
    pac = _paciente(api)
    r = api.post("/pacientes", json={"nome": "Outro", "cpf": pac["cpf"], "data_nascimento": "1990-01-01"})
    assert r.status_code == 409


def test_paciente_plano_incompleto_422(api):
    plano_id = api.get("/convenios").json()[0]["planos"][0]["id"]
    r = api.post("/pacientes", json={"nome": "X", "cpf": cpf_unico(), "data_nascimento": "1990-01-01",
                                     "plano_id": plano_id})
    assert r.status_code == 422


def test_agendamento_medico_inexistente_422(api):
    inicio, fim, *_ = _horario()
    assert _agendar(api, _paciente(api)["id"], 999999, inicio, fim).status_code == 422


def test_conflito_409(api):
    inicio, fim, base, hora = _horario()
    med = _medico_id(api)
    assert _agendar(api, _paciente(api)["id"], med, inicio, fim).status_code == 201
    r = _agendar(api, _paciente(api)["id"], med, f"{base}T{hora:02d}:15:00", f"{base}T{hora:02d}:45:00")
    assert r.status_code == 409
    assert "Horário indisponível" in r.json()["detail"]


def test_horario_encostado_ok(api):
    inicio, fim, base, hora = _horario()
    med = _medico_id(api)
    assert _agendar(api, _paciente(api)["id"], med, inicio, fim).status_code == 201
    r = _agendar(api, _paciente(api)["id"], med, fim, f"{base}T{hora + 1:02d}:00:00")
    assert r.status_code == 201


def test_periodo_invertido_422(api):
    inicio, fim, *_ = _horario()
    assert _agendar(api, _paciente(api)["id"], _medico_id(api), fim, inicio).status_code == 422


def test_data_invalida_422(api):
    assert _agendar(api, _paciente(api)["id"], _medico_id(api), "ontem", "amanhã").status_code == 422


def test_cancelar_e_reagendar(api):
    inicio, fim, *_ = _horario()
    med = _medico_id(api)
    ag = _agendar(api, _paciente(api)["id"], med, inicio, fim).json()
    assert ag["inicio"] == f"{inicio}-03:00"  # ISO completo, legível por new Date() no navegador
    assert api.post(f"/agendamentos/{ag['id']}/cancelar").status_code == 200
    assert _agendar(api, _paciente(api)["id"], med, inicio, fim).status_code == 201


def test_put_registra_auditoria_com_usuario(api):
    pac = _paciente(api)
    r = api.put(f"/pacientes/{pac['id']}", json={**pac, "telefone": "(19) 98888-7777"},
                headers={"X-Usuario": "recepcao1"})
    assert r.status_code == 200
    assert r.json()["telefone"] == "(19) 98888-7777"
    linhas = api.get("/auditoria", params={"limit": 20}).json()
    assert any(l["tabela"] == "paciente" and l["registro_id"] == pac["id"] and l["operacao"] == "UPDATE"
               and l["usuario"] == "recepcao1" for l in linhas)


def test_put_inexistente_404(api):
    body = {"nome": "X", "cpf": cpf_unico(), "data_nascimento": "1990-01-01"}
    assert api.put("/pacientes/999999", json=body).status_code == 404


def test_realizar_gera_fatura(api):
    inicio, fim, *_ = _horario()
    ag = _agendar(api, _paciente(api)["id"], _medico_id(api), inicio, fim).json()
    r = api.post(f"/agendamentos/{ag['id']}/realizar")
    assert r.status_code == 201, r.text
    f = r.json()
    assert float(f["valor_convenio"]) + float(f["valor_paciente"]) == pytest.approx(float(f["valor_total"]))
    assert any(x["id"] == f["id"] for x in api.get("/faturas").json())


def test_realizar_plano_vencido_422(api):
    carlos = api.get("/pacientes", params={"nome": "Carlos Vencido"}).json()[0]
    ags = api.get("/agendamentos", params={"paciente_id": carlos["id"]}).json()
    ag = next(a for a in ags if a["status"] == "agendado")
    r = api.post(f"/agendamentos/{ag['id']}/realizar")
    assert r.status_code == 422
    assert "vencido" in r.json()["detail"]
    depois = api.get("/agendamentos", params={"paciente_id": carlos["id"]}).json()
    assert next(a for a in depois if a["id"] == ag["id"])["status"] == "agendado"


def test_realizar_inexistente_422(api):
    assert api.post("/agendamentos/999999/realizar").status_code == 422


def test_cancelar_inexistente_404(api):
    assert api.post("/agendamentos/999999/cancelar").status_code == 404


def test_listas(api):
    for rota in ("/medicos", "/especialidades", "/convenios"):
        r = api.get(rota)
        assert r.status_code == 200 and r.json(), rota
    assert api.get("/convenios").json()[0]["planos"]
    assert api.get("/medicos").json()[0]["especialidade"]


def test_pagina_demo(api):
    r = api.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    for bloco in ('id="agenda"', 'id="faturas"', 'id="auditoria"'):
        assert bloco in r.text


def test_corrida_na_api_sem_erro_500(api):
    """Sob concorrência o Postgres pode resolver a disputa com deadlock (40P01) em vez de
    exclusion_violation. Para quem chama, os dois casos são "horário indisponível": nunca 500."""
    import asyncio

    inicio, fim, *_ = _horario()
    med = _medico_id(api)
    pacientes = [_paciente(api)["id"] for _ in range(150)]

    async def disparar():
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=60,
                                     limits=httpx.Limits(max_connections=200)) as c:
            return await asyncio.gather(*[
                c.post("/agendamentos", json={"paciente_id": p, "medico_id": med, "tipo": "consulta",
                                              "inicio": inicio, "fim": fim}) for p in pacientes])

    status = [r.status_code for r in asyncio.run(disparar())]
    assert status.count(201) == 1
    assert status.count(409) == len(pacientes) - 1, sorted(set(status))


def test_realizar_cancelado_pela_api_422(api):
    inicio, fim, *_ = _horario()
    ag = _agendar(api, _paciente(api)["id"], _medico_id(api), inicio, fim).json()
    api.post(f"/agendamentos/{ag['id']}/cancelar")
    r = api.post(f"/agendamentos/{ag['id']}/realizar")
    assert r.status_code == 422
    assert not any(f["agendamento_id"] == ag["id"] for f in api.get("/faturas").json())
