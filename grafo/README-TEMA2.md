# Tema 2 — Interações medicamentosas e rede de contato

Projeto demonstrativo de João Abilla para o Sistema de Gestão Hospitalar e Telemedicina. A pasta original implementa emergência, Redis, fila e leitos; este módulo é independente e não sincroniza pacientes ou prescrições com aquela API. IDs precisam ser informados manualmente. A aplicação original continua disponível na porta 8080.

## Executar

Com Docker e Docker Compose instalados, abra um terminal nesta pasta e execute:

```sh
docker compose -f docker-compose.yml -f docker-compose.grafo.yml up --build
```

Acesse http://localhost:8001/docs e execute POST /demonstracao. Consulte GET /pacientes/p1/riscos e GET /pacientes/p1/contatos. Cadastre nós e relações pelos demais endpoints. O Neo4j Browser fica em http://localhost:7474, usuário neo4j e senha demonstracao123. O banco persiste no volume neo4j-data. Para encerrar use `docker compose -f docker-compose.yml -f docker-compose.grafo.yml down`. Não use os dados ou a senha de demonstração em produção.

## Modelo e consultas

Nós: Paciente, Medicamento, Patologia e Profissional. Relações: USA, ALERGICO_A, TEM, CONTRAINDICADO_PARA, INTERAGE_COM, ATENDE e CONTATO_COM. A consulta de riscos percorre as prescrições e identifica pares de medicamentos relacionados, medicamentos aos quais o paciente é alérgico e medicamentos contraindicados para patologias cadastradas. A consulta de contatos lista contatos diretos; não conclui que houve transmissão. Dados de exemplo são fictícios e não representam recomendações clínicas.

A API não impede prescrições nem substitui validação clínica. A base de conhecimento deve ser revisada por profissionais, e são necessários autenticação, autorização, auditoria, proteção de dados, validação e integração antes de qualquer uso real. Não há cadastro de substâncias, dose, data ou direção clínica da interação.

## Comparação com SQL

O arquivo grafo/comparacao.sql contém um esquema e uma consulta SQL equivalentes somente para pares de interação entre medicamentos. Para medir de forma justa, popule ambos os bancos com os mesmos pacientes, medicamentos, prescrições e interações; crie índices equivalentes; confirme resultados idênticos; aqueça os bancos e execute repetidamente consultas parametrizadas com as mesmas condições. Registre volume, versões, hardware, tempos de carga, mediana e percentil 95. Use EXPLAIN/PROFILE no Neo4j e EXPLAIN QUERY PLAN no SQLite. Nenhum tempo foi medido neste projeto; não se pode concluir qual banco é mais rápido.

## Limitações e próximos passos

Adicionar restrições de unicidade e migrações, conectar os pacientes do Redis ao grafo com identificador compartilhado, registrar prescritor e período, importar uma fonte clínica confiável e implementar uma comparação automatizada com dados de volume representativo. A demonstração pressupõe IDs únicos por tipo e inserção controlada pela API.
