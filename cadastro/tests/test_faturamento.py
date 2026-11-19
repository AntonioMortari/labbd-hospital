import threading
from decimal import Decimal

import pytest
from psycopg import errors

from conftest import (conectar, nova_especialidade, novo_agendamento, novo_convenio_plano, novo_medico,
                      novo_paciente)

DIA = "2030-05-20"


def _consulta(db, plano_id=None, validade=None, valor_consulta=200.00, tipo="consulta", valor_cirurgia=None):
    med = novo_medico(db, nova_especialidade(db, valor_consulta=valor_consulta))
    pac = novo_paciente(db, plano_id=plano_id, validade=validade)
    return novo_agendamento(db, pac, med, f"{DIA} 09:00", f"{DIA} 09:30", tipo=tipo,
                            valor_cirurgia=valor_cirurgia)


def _realizar(db, ag):
    return db.execute("CALL realizar_atendimento(%s, NULL)", (ag,)).fetchone()[0]


def _fatura(db, fatura_id):
    return db.execute("SELECT valor_total, valor_convenio, valor_paciente FROM fatura WHERE id = %s",
                      (fatura_id,)).fetchone()


def _status(db, ag):
    return db.execute("SELECT status FROM agendamento WHERE id = %s", (ag,)).fetchone()[0]


def test_consulta_com_plano_70(db):
    ag = _consulta(db, plano_id=novo_convenio_plano(db, cobertura=70))
    fatura = _realizar(db, ag)
    assert _fatura(db, fatura) == (Decimal("200.00"), Decimal("140.00"), Decimal("60.00"))
    assert _status(db, ag) == "realizado"


def test_particular_convenio_paga_zero(db):
    fatura = _realizar(db, _consulta(db))
    assert _fatura(db, fatura) == (Decimal("200.00"), Decimal("0.00"), Decimal("200.00"))


def test_cirurgia_usa_valor_cirurgia(db):
    ag = _consulta(db, plano_id=novo_convenio_plano(db, cobertura=100), tipo="cirurgia", valor_cirurgia=5000)
    assert _fatura(db, _realizar(db, ag)) == (Decimal("5000.00"), Decimal("5000.00"), Decimal("0.00"))


def test_arredondamento(db):
    ag = _consulta(db, plano_id=novo_convenio_plano(db, cobertura=33.33), valor_consulta=99.99)
    assert _fatura(db, _realizar(db, ag)) == (Decimal("99.99"), Decimal("33.33"), Decimal("66.66"))


def test_plano_vencido_desfaz_tudo(db):
    ag = _consulta(db, plano_id=novo_convenio_plano(db), validade="2030-05-19")
    db.commit()  # o agendamento precisa existir fora da transação que vai falhar
    try:
        with pytest.raises(errors.RaiseException, match="vencido"):
            _realizar(db, ag)
        db.rollback()
        with conectar() as outra:
            assert _status(outra, ag) == "agendado"
            assert outra.execute("SELECT count(*) FROM fatura WHERE agendamento_id = %s", (ag,)).fetchone()[0] == 0
    finally:
        db.rollback()
        db.execute("DELETE FROM agendamento WHERE id = %s", (ag,))
        db.commit()


def test_validade_no_dia_ok(db):
    ag = _consulta(db, plano_id=novo_convenio_plano(db), validade=DIA)
    assert _realizar(db, ag) is not None


def test_cancelado_nao_fatura(db):
    ag = _consulta(db)
    db.execute("UPDATE agendamento SET status = 'cancelado' WHERE id = %s", (ag,))
    with pytest.raises(errors.RaiseException, match="não pode ser realizado"):
        _realizar(db, ag)


def test_ja_realizado_nao_fatura(db):
    ag = _consulta(db)
    _realizar(db, ag)
    with pytest.raises(errors.RaiseException, match="não pode ser realizado"):
        _realizar(db, ag)


def test_inexistente(db):
    with pytest.raises(errors.RaiseException, match="não encontrado"):
        _realizar(db, 999999)


def test_duas_chamadas_simultaneas(db_commit):
    ag = _consulta(db_commit)
    barreira = threading.Barrier(2)
    resultados = []

    def tentar():
        with conectar() as conn:
            barreira.wait()
            try:
                _realizar(conn, ag)
                conn.commit()
                resultados.append("ok")
            except errors.RaiseException:
                conn.rollback()
                resultados.append("recusado")

    threads = [threading.Thread(target=tentar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(resultados) == ["ok", "recusado"]
    assert db_commit.execute("SELECT count(*) FROM fatura WHERE agendamento_id = %s", (ag,)).fetchone()[0] == 1


def test_realizado_nao_pode_ser_cancelado(db):
    ag = _consulta(db)
    _realizar(db, ag)
    with pytest.raises(errors.RaiseException, match="não pode mudar"):
        db.execute("UPDATE agendamento SET status = 'cancelado' WHERE id = %s", (ag,))


def test_cancelado_nao_volta_a_agendado(db):
    ag = _consulta(db)
    db.execute("UPDATE agendamento SET status = 'cancelado' WHERE id = %s", (ag,))
    with pytest.raises(errors.RaiseException, match="não pode mudar"):
        db.execute("UPDATE agendamento SET status = 'agendado' WHERE id = %s", (ag,))


def test_agendado_pode_ser_cancelado(db):
    ag = _consulta(db)
    db.execute("UPDATE agendamento SET status = 'cancelado' WHERE id = %s", (ag,))
    assert _status(db, ag) == "cancelado"
