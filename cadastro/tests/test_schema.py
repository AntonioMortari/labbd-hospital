import threading

import psycopg
import pytest
from psycopg import errors

from conftest import (conectar, cpf_unico, nova_especialidade, novo_agendamento, novo_convenio_plano,
                      novo_medico, novo_paciente)

DIA = "2030-03-15"


def _medico(db):
    return novo_medico(db, nova_especialidade(db))


def test_cpf_duplicado(db):
    cpf = cpf_unico()
    novo_paciente(db, cpf=cpf)
    with pytest.raises(errors.UniqueViolation):
        novo_paciente(db, cpf=cpf)


def test_cpf_invalido(db):
    with pytest.raises(errors.CheckViolation):
        novo_paciente(db, cpf="123")


def test_plano_sem_carteirinha(db):
    plano = novo_convenio_plano(db)
    with pytest.raises(errors.CheckViolation):
        db.execute("""INSERT INTO paciente (nome, cpf, data_nascimento, plano_id)
                      VALUES ('X', %s, '1990-01-01', %s)""", (cpf_unico(), plano))


def test_nascimento_no_futuro(db):
    with pytest.raises(errors.CheckViolation):
        db.execute("INSERT INTO paciente (nome, cpf, data_nascimento) VALUES ('X', %s, current_date + 1)",
                   (cpf_unico(),))


def test_medico_com_especialidade_inexistente(db):
    with pytest.raises(errors.ForeignKeyViolation):
        novo_medico(db, 999999)


def test_apagar_medico_com_agendamento(db):
    med = _medico(db)
    novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:00", f"{DIA} 09:30")
    with pytest.raises(errors.ForeignKeyViolation):
        db.execute("DELETE FROM medico WHERE id = %s", (med,))


def test_cirurgia_sem_valor(db):
    with pytest.raises(errors.CheckViolation):
        novo_agendamento(db, novo_paciente(db), _medico(db), f"{DIA} 09:00", f"{DIA} 11:00", tipo="cirurgia")


def test_conflito_mesmo_medico(db):
    med = _medico(db)
    novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:00", f"{DIA} 09:30")
    with pytest.raises(errors.ExclusionViolation):
        novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:15", f"{DIA} 09:45")


def test_conflito_mesmo_paciente(db):
    pac = novo_paciente(db)
    novo_agendamento(db, pac, _medico(db), f"{DIA} 09:00", f"{DIA} 09:30")
    with pytest.raises(errors.ExclusionViolation):
        novo_agendamento(db, pac, _medico(db), f"{DIA} 09:15", f"{DIA} 09:45")


def test_horarios_encostados_ok(db):
    med = _medico(db)
    novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:00", f"{DIA} 09:30")
    novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:30", f"{DIA} 10:00")


def test_cancelado_libera_horario(db):
    med = _medico(db)
    ag = novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:00", f"{DIA} 09:30")
    db.execute("UPDATE agendamento SET status = 'cancelado' WHERE id = %s", (ag,))
    novo_agendamento(db, novo_paciente(db), med, f"{DIA} 09:00", f"{DIA} 09:30")


def test_status_invalido(db):
    ag = novo_agendamento(db, novo_paciente(db), _medico(db), f"{DIA} 09:00", f"{DIA} 09:30")
    with pytest.raises(errors.CheckViolation):
        db.execute("UPDATE agendamento SET status = 'perdido' WHERE id = %s", (ag,))


def test_periodo_invertido(db):
    with pytest.raises(psycopg.errors.DataException):
        novo_agendamento(db, novo_paciente(db), _medico(db), f"{DIA} 10:00", f"{DIA} 09:00")


def test_periodo_vazio(db):
    with pytest.raises(errors.CheckViolation):
        novo_agendamento(db, novo_paciente(db), _medico(db), f"{DIA} 10:00", f"{DIA} 10:00")


def test_hora_sem_fuso_e_sao_paulo(db):
    ag = novo_agendamento(db, novo_paciente(db), _medico(db), "2026-11-27 09:00", "2026-11-27 09:30")
    ok = db.execute("SELECT lower(periodo) = '2026-11-27 12:00+00'::timestamptz FROM agendamento WHERE id = %s",
                    (ag,)).fetchone()[0]
    assert ok


def test_fatura_soma_errada(db):
    ag = novo_agendamento(db, novo_paciente(db), _medico(db), f"{DIA} 09:00", f"{DIA} 09:30")
    with pytest.raises(errors.CheckViolation):
        db.execute("""INSERT INTO fatura (agendamento_id, valor_total, valor_convenio, valor_paciente)
                      VALUES (%s, 100, 50, 10)""", (ag,))


def test_corrida_mesmo_horario(db_commit):
    esp = nova_especialidade(db_commit)
    med = novo_medico(db_commit, esp)
    pacientes = [novo_paciente(db_commit) for _ in range(20)]
    barreira = threading.Barrier(20, timeout=30)
    resultados = []

    def tentar(pac):
        with conectar() as conn:
            barreira.wait()
            try:
                novo_agendamento(conn, pac, med, "2030-04-01 07:00", "2030-04-01 07:30")
                conn.commit()
                resultados.append("ok")
            except errors.ExclusionViolation:
                conn.rollback()
                resultados.append("conflito")

    threads = [threading.Thread(target=tentar, args=(p,)) for p in pacientes]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert resultados.count("ok") == 1
        assert resultados.count("conflito") == 19
    finally:
        db_commit.execute("DELETE FROM agendamento WHERE medico_id = %s", (med,))
        db_commit.execute("DELETE FROM paciente WHERE id = ANY(%s)", (pacientes,))
        db_commit.execute("DELETE FROM medico WHERE id = %s", (med,))
        db_commit.execute("DELETE FROM especialidade WHERE id = %s", (esp,))

