-- =============================================================
-- 04: dados de exemplo para a demonstração
-- Datas relativas a current_date: a demo funciona em qualquer dia.
-- =============================================================

-- As inserções abaixo também passam pelo trigger de auditoria
SELECT set_config('app.usuario', 'carga-inicial', false);

INSERT INTO especialidade (nome, valor_consulta) VALUES
    ('Clínica Geral', 150.00),
    ('Cardiologia',   300.00),
    ('Ortopedia',     250.00),
    ('Pediatria',     180.00);

INSERT INTO convenio (nome, cnpj) VALUES
    ('Saúde Total', '11222333000144'),
    ('VidaMais',    '55666777000188');

INSERT INTO plano (convenio_id, nome, cobertura_pct) VALUES
    ((SELECT id FROM convenio WHERE nome = 'Saúde Total'), 'Básico',     70),
    ((SELECT id FROM convenio WHERE nome = 'Saúde Total'), 'Premium',   100),
    ((SELECT id FROM convenio WHERE nome = 'VidaMais'),    'Essencial',  50),
    ((SELECT id FROM convenio WHERE nome = 'VidaMais'),    'Plus',       80);

INSERT INTO medico (nome, crm, especialidade_id)
SELECT m.nome, m.crm, e.id
  FROM (VALUES
        (1, 'Dra. Marina Costa', 'CRM-SP 100001', 'Clínica Geral'),
        (2, 'Dr. Paulo Mendes',  'CRM-SP 100002', 'Cardiologia'),
        (3, 'Dra. Renata Dias',  'CRM-SP 100003', 'Ortopedia'),
        (4, 'Dr. Sérgio Pinto',  'CRM-SP 100004', 'Pediatria'),
        (5, 'Dr. Tiago Ramos',   'CRM-SP 100005', 'Clínica Geral'),
        (6, 'Dra. Vera Lopes',   'CRM-SP 100006', 'Cardiologia')
       ) AS m(ordem, nome, crm, especialidade)
  JOIN especialidade e ON e.nome = m.especialidade
 ORDER BY m.ordem;

-- Planos: (convênio, plano) ou NULL para particular
INSERT INTO paciente (nome, cpf, data_nascimento, telefone, plano_id, carteirinha, validade_carteirinha)
SELECT p.nome, p.cpf, p.nascimento, p.telefone, pl.id, p.carteirinha, p.validade
  FROM (VALUES
        (1, 'Ana Souza',       '00000000001', date '1985-03-12', '(19) 99111-0001', 'Saúde Total', 'Básico',    'ST-0001', current_date + 365),
        (2, 'Carlos Vencido',  '00000000002', date '1972-08-30', '(19) 99111-0002', 'Saúde Total', 'Básico',    'ST-0002', current_date - 30),
        (3, 'Beatriz Lima',    '00000000003', date '1990-11-05', '(19) 99111-0003', 'Saúde Total', 'Premium',   'ST-0003', current_date + 365),
        (4, 'Diego Martins',   '00000000004', date '1968-01-22', '(19) 99111-0004', 'VidaMais',    'Essencial', 'VM-0004', current_date + 365),
        (5, 'Elisa Rocha',     '00000000005', date '2001-06-17', '(19) 99111-0005', 'VidaMais',    'Plus',      'VM-0005', current_date + 365),
        (6, 'Fábio Nunes',     '00000000006', date '1995-09-09', '(19) 99111-0006', NULL,          NULL,        NULL,      NULL::date),
        (7, 'Gabriela Torres', '00000000007', date '2015-04-01', '(19) 99111-0007', NULL,          NULL,        NULL,      NULL::date),
        (8, 'Henrique Alves',  '00000000008', date '1958-12-25', '(19) 99111-0008', 'VidaMais',    'Essencial', 'VM-0008', current_date + 365)
       ) AS p(ordem, nome, cpf, nascimento, telefone, convenio, plano, carteirinha, validade)
  LEFT JOIN convenio c ON c.nome = p.convenio
  LEFT JOIN plano pl   ON pl.convenio_id = c.id AND pl.nome = p.plano
 ORDER BY p.ordem;

-- Agendamentos entre amanhã e daqui a 11 dias (horários a partir das 08:00, sem conflito)
INSERT INTO agendamento (paciente_id, medico_id, tipo, periodo, valor_cirurgia)
SELECT pa.id, me.id, a.tipo,
       tstzrange((current_date + a.dias) + a.inicio, (current_date + a.dias) + a.fim, '[)'),
       a.valor_cirurgia
  FROM (VALUES
        (1, '00000000001', 'CRM-SP 100001', 'consulta', 1,  time '08:00', time '08:30', NULL::numeric),
        (2, '00000000002', 'CRM-SP 100002', 'consulta', 1,  time '09:00', time '09:30', NULL),
        (3, '00000000003', 'CRM-SP 100002', 'consulta', 2,  time '10:00', time '10:30', NULL),
        (4, '00000000004', 'CRM-SP 100003', 'cirurgia', 4,  time '08:00', time '11:00', 8000.00),
        (5, '00000000006', 'CRM-SP 100005', 'consulta', 7,  time '14:00', time '14:30', NULL),
        (6, '00000000007', 'CRM-SP 100004', 'consulta', 11, time '15:00', time '15:30', NULL)
       ) AS a(ordem, cpf, crm, tipo, dias, inicio, fim, valor_cirurgia)
  JOIN paciente pa ON pa.cpf = a.cpf
  JOIN medico   me ON me.crm = a.crm
 ORDER BY a.ordem;
