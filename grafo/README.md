# Tema 2 — Interações medicamentosas e rede de contato (Neo4j)

Autor: João Abilla. Módulo do sistema hospitalar, independente dos outros: tem a própria pasta, o próprio compose e o próprio banco.
O projeto original da entrega está descrito em [`README-TEMA2.md`](README-TEMA2.md) e o roteiro em [`APRESENTACAO.md`](APRESENTACAO.md).

## Rodar

```bash
cd grafo
docker compose up -d --build     # Neo4j + API, em http://localhost:8082
```

Ou pelo sistema completo (`python3 integracao/sistema.py subir grafo`), que abre o módulo na aba **Interações** de http://localhost:8000.
O Neo4j Browser fica em http://localhost:7474 (usuário `neo4j`, senha `demonstracao123`: só para demonstração).

## O que tem na interface

- **Riscos:** escolha um paciente e veja interações entre medicamentos em uso, alergias, contraindicações e contatos, com o Cypher e o tempo de cada consulta.
- **Rede:** o grafo desenhado em colunas (profissionais, pacientes, medicamentos, patologias); clique num nó para destacar as ligações.
- **Cadastrar:** carregar a demonstração, importar os pacientes do cadastro (Tema 1), criar nós e relações, limpar o grafo.
- **Grafo vs SQL:** a mesma pergunta em Cypher e em SQL. Nenhum tempo foi medido (veja `README-TEMA2.md`).

## O que foi acrescentado à entrega original

Os endpoints originais (`/nos`, `/relacoes`, `/pacientes/{id}/riscos`, `/contatos`, `/demonstracao`) ficaram como estavam. Acrescentamos:
`/health` (exigido pelo contrato do sistema), `GET /grafo`, `GET /pacientes/{id}/analise`, `POST /demonstracao/completa`, `DELETE /grafo`,
restrições de unicidade por tipo de nó e a interface em `static/`. A porta do módulo é 8082 (era 8001).

## Identidade do paciente

O Tema 1 é o dono do cadastro. O nó `Paciente` guarda só o código (o `id` do cadastro, como texto) e o nome copiado na importação.
Dados de exemplo são fictícios e não são recomendação clínica.
