-- =============================================================
-- 03: faturamento transacional ligado ao plano de saúde
-- =============================================================
-- Uso:  CALL realizar_atendimento(<agendamento_id>, NULL);   -- devolve p_fatura_id
--
-- Tudo acontece numa única transação: marcar o atendimento como realizado,
-- calcular a parte do convênio e a do paciente e emitir a fatura.
-- Qualquer erro (plano vencido, status inválido...) desfaz tudo.

CREATE PROCEDURE realizar_atendimento(p_agendamento_id int, INOUT p_fatura_id int DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
    v_ag        agendamento%ROWTYPE;
    v_pac       paciente%ROWTYPE;
    v_data      date;
    v_total     numeric(10,2);
    v_cobertura numeric(5,2) := 0;
    v_convenio  numeric(10,2);
BEGIN
    -- Trava a linha: duas chamadas simultâneas para o mesmo agendamento
    -- são serializadas e a segunda já encontra o status 'realizado'.
    SELECT * INTO v_ag FROM agendamento WHERE id = p_agendamento_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Agendamento % não encontrado', p_agendamento_id USING ERRCODE = 'P0001';
    END IF;
    IF v_ag.status <> 'agendado' THEN
        RAISE EXCEPTION 'Agendamento % não pode ser realizado (status: %)', p_agendamento_id, v_ag.status
            USING ERRCODE = 'P0001';
    END IF;

    v_data := lower(v_ag.periodo)::date;

    -- Valor: cirurgia tem valor próprio; consulta usa o valor da especialidade do médico
    IF v_ag.tipo = 'cirurgia' THEN
        v_total := v_ag.valor_cirurgia;
    ELSE
        SELECT e.valor_consulta INTO v_total
          FROM medico m JOIN especialidade e ON e.id = m.especialidade_id
         WHERE m.id = v_ag.medico_id;
    END IF;

    -- Cobertura do plano (particular: convênio não paga nada)
    SELECT * INTO v_pac FROM paciente WHERE id = v_ag.paciente_id;
    IF v_pac.plano_id IS NOT NULL THEN
        IF v_pac.validade_carteirinha < v_data THEN
            RAISE EXCEPTION 'Plano do paciente vencido em %', to_char(v_pac.validade_carteirinha, 'DD/MM/YYYY')
                USING ERRCODE = 'P0001';
        END IF;
        SELECT cobertura_pct INTO v_cobertura FROM plano WHERE id = v_pac.plano_id;
    END IF;

    v_convenio := round(v_total * v_cobertura / 100, 2);

    INSERT INTO fatura (agendamento_id, valor_total, valor_convenio, valor_paciente)
    VALUES (p_agendamento_id, v_total, v_convenio, v_total - v_convenio)
    RETURNING id INTO p_fatura_id;

    UPDATE agendamento SET status = 'realizado' WHERE id = p_agendamento_id;
END;
$$;
