"""O seed é identificado por nomes/códigos fixos, porque outros testes (e o loadtest)
também gravam dados no mesmo banco."""

SEED_CPFS = "cpf BETWEEN '00000000001' AND '00000000008'"


def _um(db, sql):
    return db.execute(sql).fetchone()[0]


def test_especialidades(db):
    assert _um(db, """SELECT count(*) FROM especialidade
                      WHERE nome IN ('Clínica Geral', 'Cardiologia', 'Ortopedia', 'Pediatria')""") == 4


def test_convenios_e_planos(db):
    assert _um(db, "SELECT count(*) FROM convenio WHERE nome IN ('Saúde Total', 'VidaMais')") == 2
    assert _um(db, """SELECT count(*) FROM plano p JOIN convenio c ON c.id = p.convenio_id
                      WHERE c.nome IN ('Saúde Total', 'VidaMais')""") == 4


def test_medicos(db):
    assert _um(db, "SELECT count(*) FROM medico WHERE crm LIKE 'CRM-SP 10000_'") == 6
    primeiro = _um(db, """SELECT e.nome FROM medico m JOIN especialidade e ON e.id = m.especialidade_id
                          ORDER BY m.id LIMIT 1""")
    assert primeiro == "Clínica Geral"


def test_pacientes(db):
    assert _um(db, f"SELECT count(*) FROM paciente WHERE {SEED_CPFS}") == 8
    assert _um(db, f"SELECT count(*) FROM paciente WHERE {SEED_CPFS} AND plano_id IS NULL") >= 2


def test_paciente_vencido(db):
    assert _um(db, """SELECT validade_carteirinha < current_date FROM paciente
                      WHERE cpf = '00000000002' AND nome = 'Carlos Vencido'""") is True


def test_agendamentos_futuros(db):
    assert _um(db, f"""SELECT count(*) FROM agendamento a JOIN paciente p ON p.id = a.paciente_id
                       WHERE p.{SEED_CPFS} AND a.status = 'agendado'
                         AND lower(a.periodo) >= current_date + 1
                         AND lower(a.periodo) <  current_date + 12""") >= 6


def test_vencido_tem_agendamento(db):
    assert _um(db, """SELECT count(*) FROM agendamento a JOIN paciente p ON p.id = a.paciente_id
                      WHERE p.cpf = '00000000002' AND a.status = 'agendado'""") >= 1
