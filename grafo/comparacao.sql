-- Modelo relacional equivalente para interação medicamentosa; compatível com SQLite.
CREATE TABLE paciente(id TEXT PRIMARY KEY, nome TEXT NOT NULL);
CREATE TABLE medicamento(id TEXT PRIMARY KEY, nome TEXT NOT NULL);
CREATE TABLE uso(paciente_id TEXT, medicamento_id TEXT, PRIMARY KEY(paciente_id, medicamento_id));
CREATE TABLE interacao(medicamento_a TEXT, medicamento_b TEXT, observacao TEXT, PRIMARY KEY(medicamento_a, medicamento_b));
CREATE INDEX uso_medicamento ON uso(medicamento_id);
-- Uma linha por par, independentemente da orientação do registro da interação.
SELECT DISTINCT a.nome AS medicamento, b.nome AS relacionado, i.observacao
FROM uso u1 JOIN uso u2 ON u1.paciente_id = u2.paciente_id AND u1.medicamento_id < u2.medicamento_id
JOIN medicamento a ON a.id = u1.medicamento_id JOIN medicamento b ON b.id = u2.medicamento_id
JOIN interacao i ON (i.medicamento_a = a.id AND i.medicamento_b = b.id) OR (i.medicamento_a = b.id AND i.medicamento_b = a.id)
WHERE u1.paciente_id = ?;
