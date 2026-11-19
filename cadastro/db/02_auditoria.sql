-- =============================================================
-- 02: auditoria de cadastros sensíveis (trigger + função PL/pgSQL)
-- =============================================================

CREATE TABLE auditoria (
    id            bigserial PRIMARY KEY,
    tabela        text  NOT NULL,
    operacao      text  NOT NULL CHECK (operacao IN ('INSERT', 'UPDATE', 'DELETE')),
    registro_id   int   NOT NULL,
    dados_antigos jsonb,           -- NULL em INSERT
    dados_novos   jsonb,           -- NULL em DELETE
    usuario       text  NOT NULL,
    em            timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX auditoria_registro ON auditoria (tabela, registro_id);

-- Quem alterou: a API informa o usuário da aplicação em cada transação com
--   SELECT set_config('app.usuario', '<usuario>', true);
-- Sem isso, fica registrado o usuário do banco (current_user).
CREATE FUNCTION fn_auditoria() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_usuario text := coalesce(nullif(current_setting('app.usuario', true), ''), current_user);
BEGIN
    IF TG_OP = 'UPDATE' AND OLD IS NOT DISTINCT FROM NEW THEN
        RETURN NULL;  -- nada mudou, nada a auditar
    END IF;

    INSERT INTO auditoria (tabela, operacao, registro_id, dados_antigos, dados_novos, usuario)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END,
        CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
        CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END,
        v_usuario
    );
    RETURN NULL;  -- trigger AFTER: o valor de retorno é ignorado
END;
$$;

CREATE TRIGGER trg_auditoria_paciente
    AFTER INSERT OR UPDATE OR DELETE ON paciente
    FOR EACH ROW EXECUTE FUNCTION fn_auditoria();

CREATE TRIGGER trg_auditoria_medico
    AFTER INSERT OR UPDATE OR DELETE ON medico
    FOR EACH ROW EXECUTE FUNCTION fn_auditoria();

CREATE TRIGGER trg_auditoria_plano
    AFTER INSERT OR UPDATE OR DELETE ON plano
    FOR EACH ROW EXECUTE FUNCTION fn_auditoria();

-- A trilha de auditoria só cresce: alterar, apagar ou truncar é recusado pelo banco.
CREATE FUNCTION fn_auditoria_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'A auditoria não pode ser alterada (% recusado)', TG_OP USING ERRCODE = 'P0001';
END;
$$;

CREATE TRIGGER trg_auditoria_imutavel
    BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION fn_auditoria_imutavel();

CREATE TRIGGER trg_auditoria_sem_truncate
    BEFORE TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION fn_auditoria_imutavel();
