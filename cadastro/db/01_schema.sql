-- =============================================================
-- Tema 1 — Cadastro de Pacientes, Equipe Médica e Agendamentos
-- 01: tabelas e regras de integridade
-- =============================================================

-- Necessária para usar "=" em inteiros dentro de uma exclusion constraint (GiST)
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE especialidade (
    id             serial PRIMARY KEY,
    nome           text          NOT NULL UNIQUE,
    valor_consulta numeric(10,2) NOT NULL CHECK (valor_consulta > 0)
);

CREATE TABLE convenio (
    id   serial PRIMARY KEY,
    nome text     NOT NULL UNIQUE,
    cnpj char(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$')
);

CREATE TABLE plano (
    id            serial PRIMARY KEY,
    convenio_id   int          NOT NULL REFERENCES convenio (id),
    nome          text         NOT NULL,
    cobertura_pct numeric(5,2) NOT NULL CHECK (cobertura_pct BETWEEN 0 AND 100),
    UNIQUE (convenio_id, nome)
);

CREATE TABLE paciente (
    id                   serial PRIMARY KEY,
    nome                 text     NOT NULL,
    cpf                  char(11) NOT NULL UNIQUE CHECK (cpf ~ '^[0-9]{11}$'),
    data_nascimento      date     NOT NULL CHECK (data_nascimento <= current_date),
    telefone             text,
    plano_id             int REFERENCES plano (id),          -- NULL = particular
    carteirinha          text,
    validade_carteirinha date,
    -- ou o paciente é particular (tudo nulo) ou tem plano completo (tudo preenchido)
    CONSTRAINT plano_completo CHECK (
        (plano_id IS NULL) = (carteirinha IS NULL)
        AND (plano_id IS NULL) = (validade_carteirinha IS NULL)
    )
);

CREATE TABLE medico (
    id               serial PRIMARY KEY,
    nome             text NOT NULL,
    crm              text NOT NULL UNIQUE,
    especialidade_id int  NOT NULL REFERENCES especialidade (id)
);

CREATE TABLE agendamento (
    id             serial PRIMARY KEY,
    paciente_id    int       NOT NULL REFERENCES paciente (id),
    medico_id      int       NOT NULL REFERENCES medico (id),
    tipo           text      NOT NULL CHECK (tipo IN ('consulta', 'cirurgia')),
    periodo        tstzrange NOT NULL CHECK (NOT isempty(periodo)),
    status         text      NOT NULL DEFAULT 'agendado'
                             CHECK (status IN ('agendado', 'realizado', 'cancelado')),
    valor_cirurgia numeric(10,2) CHECK (valor_cirurgia > 0),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    -- cirurgia tem valor próprio; consulta usa o valor da especialidade
    CONSTRAINT valor_so_em_cirurgia CHECK ((tipo = 'cirurgia') = (valor_cirurgia IS NOT NULL)),
    -- CONTROLE DE CONCORRÊNCIA: o banco recusa horários sobrepostos para o mesmo médico
    -- ou para o mesmo paciente, mesmo com transações simultâneas. Cancelados liberam o horário.
    CONSTRAINT sem_conflito_medico
        EXCLUDE USING gist (medico_id WITH =, periodo WITH &&) WHERE (status <> 'cancelado'),
    CONSTRAINT sem_conflito_paciente
        EXCLUDE USING gist (paciente_id WITH =, periodo WITH &&) WHERE (status <> 'cancelado')
);

-- FILA POR MÉDICO (bloqueio pessimista)
-- Sem isto, centenas de inserções simultâneas no mesmo intervalo se esperam umas às outras dentro
-- da exclusion constraint e o Postgres precisa desfazer parte delas por deadlock (~1 s para detectar
-- cada um). Travando antes a linha do médico, as tentativas para o mesmo médico entram em fila:
-- cada uma, na sua vez, já encontra o conflito gravado e falha na hora com exclusion_violation.
-- A garantia continua sendo a constraint; o trigger só organiza a disputa.
-- FOR NO KEY UPDATE não bloqueia as checagens de chave estrangeira de outras transações.
CREATE FUNCTION fn_fila_por_medico() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM medico WHERE id = NEW.medico_id FOR NO KEY UPDATE;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_fila_por_medico
    BEFORE INSERT OR UPDATE OF medico_id, periodo, status ON agendamento
    FOR EACH ROW EXECUTE FUNCTION fn_fila_por_medico();

CREATE TABLE fatura (
    id             serial PRIMARY KEY,
    agendamento_id int           NOT NULL UNIQUE REFERENCES agendamento (id),
    valor_total    numeric(10,2) NOT NULL CHECK (valor_total >= 0),
    valor_convenio numeric(10,2) NOT NULL CHECK (valor_convenio >= 0),
    valor_paciente numeric(10,2) NOT NULL CHECK (valor_paciente >= 0),
    emitida_em     timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT soma_confere CHECK (valor_convenio + valor_paciente = valor_total)
);

-- TRANSIÇÕES DE STATUS: agendado -> realizado | cancelado. Realizado e cancelado são finais.
-- Garantido no banco: nem pelo psql/DBeaver dá para "cancelar" um atendimento já faturado.
CREATE FUNCTION fn_transicao_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND OLD.status <> 'agendado' THEN
        RAISE EXCEPTION 'Agendamento % está % e não pode mudar para %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'P0001', CONSTRAINT = 'trg_transicao_status';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_transicao_status
    BEFORE UPDATE OF status ON agendamento
    FOR EACH ROW EXECUTE FUNCTION fn_transicao_status();
