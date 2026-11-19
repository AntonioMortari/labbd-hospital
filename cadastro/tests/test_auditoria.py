import pytest
from psycopg import errors

from conftest import nova_especialidade, novo_convenio_plano, novo_medico, novo_paciente


def _ultima(db, tabela, registro_id):
    return db.execute(
        """SELECT operacao, dados_antigos, dados_novos, usuario FROM auditoria
           WHERE tabela = %s AND registro_id = %s ORDER BY id DESC LIMIT 1""",
        (tabela, registro_id)).fetchone()


def _contar(db, tabela, registro_id):
    return db.execute("SELECT count(*) FROM auditoria WHERE tabela = %s AND registro_id = %s",
                      (tabela, registro_id)).fetchone()[0]


def test_update_paciente_registra_antes_e_depois(db):
    pac = novo_paciente(db)
    db.execute("UPDATE paciente SET telefone = '1111' WHERE id = %s", (pac,))
    db.execute("SELECT set_config('app.usuario', 'recepcao1', true)")
    db.execute("UPDATE paciente SET telefone = '2222' WHERE id = %s", (pac,))
    operacao, antigos, novos, usuario = _ultima(db, "paciente", pac)
    assert operacao == "UPDATE"
    assert antigos["telefone"] == "1111"
    assert novos["telefone"] == "2222"
    assert usuario == "recepcao1"


def test_insert_e_delete_registrados(db):
    pac = novo_paciente(db)
    operacao, antigos, novos, _ = _ultima(db, "paciente", pac)
    assert (operacao, antigos) == ("INSERT", None)
    assert novos["id"] == pac
    db.execute("DELETE FROM paciente WHERE id = %s", (pac,))
    operacao, antigos, novos, _ = _ultima(db, "paciente", pac)
    assert (operacao, novos) == ("DELETE", None)
    assert antigos["id"] == pac


def test_update_sem_mudanca_nao_registra(db):
    pac = novo_paciente(db)
    antes = _contar(db, "paciente", pac)
    db.execute("UPDATE paciente SET nome = nome WHERE id = %s", (pac,))
    assert _contar(db, "paciente", pac) == antes


def test_sem_usuario_usa_current_user(db):
    pac = novo_paciente(db)
    assert _ultima(db, "paciente", pac)[3] == "postgres"


def test_medico_e_plano_auditados(db):
    med = novo_medico(db, nova_especialidade(db))
    db.execute("UPDATE medico SET nome = 'Dr Alterado' WHERE id = %s", (med,))
    assert _ultima(db, "medico", med)[0] == "UPDATE"
    plano = novo_convenio_plano(db, cobertura=70)
    db.execute("UPDATE plano SET cobertura_pct = 80 WHERE id = %s", (plano,))
    operacao, antigos, novos, _ = _ultima(db, "plano", plano)
    assert operacao == "UPDATE"
    assert (float(antigos["cobertura_pct"]), float(novos["cobertura_pct"])) == (70.0, 80.0)


def test_auditoria_nao_pode_ser_alterada(db):
    pac = novo_paciente(db)
    with pytest.raises(errors.RaiseException, match="não pode ser alterada"):
        db.execute("UPDATE auditoria SET usuario = 'outro' WHERE tabela = 'paciente' AND registro_id = %s", (pac,))


def test_auditoria_nao_pode_ser_apagada(db):
    pac = novo_paciente(db)
    with pytest.raises(errors.RaiseException, match="não pode ser alterada"):
        db.execute("DELETE FROM auditoria WHERE tabela = 'paciente' AND registro_id = %s", (pac,))


def test_auditoria_nao_pode_ser_truncada(db):
    with pytest.raises(errors.RaiseException, match="não pode ser alterada"):
        db.execute("TRUNCATE auditoria")
