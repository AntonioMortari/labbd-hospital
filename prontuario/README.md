# Tema 4 — Prontuário Eletrônico do Paciente (MongoDB)

Autor do banco: Gustavo. Módulo do sistema hospitalar, independente dos outros (própria pasta, compose e banco).

## Rodar

```bash
cd prontuario
docker compose up -d --build                  # MongoDB + API, em http://localhost:8084
docker compose --profile test run --rm tests  # 10 testes
```

Ou pelo sistema completo (`python3 integracao/sistema.py subir prontuario`), na aba **Prontuário** de http://localhost:8000.
Na primeira subida o backup entregue (`db/dump/`, de `prontuario_medico.zip`) é restaurado sozinho no MongoDB.
Para recomeçar do zero: `docker compose down -v` (apaga o volume e restaura o backup de novo).

## Modelo

- `prontuarios`: um documento por paciente, com histórico clínico, evoluções, exames (campos livres por tipo de exame) e prescrições embutidos.
- `historico_versoes`: a cópia de cada versão anterior, com a auditoria (responsável, data e justificativa).

Toda alteração exige responsável e justificativa. A API grava primeiro a cópia da versão N (índice único por prontuário e versão)
e só então atualiza o documento, se a versão ainda for N. Duas alterações simultâneas não se sobrescrevem: a segunda recebe 409.

## O que há na interface

- **Prontuário:** histórico, evoluções (com "Corrigir"), exames, prescrições. Cada ação pede responsável e justificativa.
- **Versões:** a linha do tempo das alterações, com o que mudou em cada uma e a versão completa de cada momento.
- **MongoDB por dentro:** coleções, índices e um documento de exemplo, com a explicação do modelo.
- **Carregar exemplos:** cria prontuários fictícios para os pacientes 1 e 2 do cadastro.

## Notas

- O backup usa `paciente_id` 1001 e `medico_id` 101, que não existem no cadastro (Tema 1, ids de 1 a 8). A interface mostra esses como
  "fora do cadastro". Os prontuários criados pela interface usam pacientes e médicos do cadastro.
- O docx do grupo prevê PHP; como só o backup do banco foi entregue, a API foi escrita em Python (FastAPI), como os outros módulos.
- Guia de instalação e plano do grupo em `docs/`. Senha do banco só para demonstração.
