# LabBD — Sistema de Gestão Hospitalar e Telemedicina

Seminário final (P2) de Laboratório de Banco de Dados · Prof. Eduardo Freitas · apresentação em 27/11/2026

Cinco módulos, cada um com um tipo de banco de dados:

| Tema | Módulo | Pasta | Banco | Responsáveis |
|---|---|---|---|---|
| 1 | Cadastro, Equipe Médica e Agendamentos | [`cadastro/`](cadastro/) | PostgreSQL | Yuri e Antônio |
| 2 | Interações Medicamentosas e Rede de Contágio | `grafo/` | grafos | João Abilla |
| 3 | Fila de Triagem, Leitos e Cache Operacional | `emergencia/` | Redis | Stéfano Ferrari |
| 4 | Prontuário Eletrônico (PEP) | `prontuario/` | documentos | Gustavo |
| 5 | Monitoramento de Sinais Vitais | `sinais/` | série temporal | Ricardo, Felipe Batista, Daiane e Brun |

Neste repositório estão `cadastro/`, `grafo/` (Tema 2, do João), `emergencia/` (Tema 3, do Stéfano) e `prontuario/` (Tema 4, do Gustavo). As outras entram como pastas irmãs, no mesmo formato.

## Sistema completo

```bash
python3 integracao/sistema.py subir     # sobe os módulos que já têm pasta e o gateway
python3 integracao/sistema.py status    # quem está no ar
```

Abra **http://localhost:8000**: é uma aplicação só, com uma aba por módulo (cada um com o seu banco) e o estado de cada
um ao vivo. Por baixo, cada módulo continua independente, com o seu endereço (`cadastro.localhost:8000`,
`triagem.localhost:8000`...) e abre dentro das abas. O Tema 1 é o dono do cadastro de pacientes, e os outros temas
guardam só o `paciente_id`.

**Para plugar o seu módulo:** [`integracao/CONTRATO.md`](integracao/CONTRATO.md) (são 4 regras) e o
[`integracao/modelo-modulo/`](integracao/modelo-modulo/) para começar.

## Só o Tema 1

```bash
cd cadastro
docker compose up -d --build                 # Postgres, 3 APIs e Nginx, em http://localhost:8081
docker compose --profile test run --rm tests # 82 testes
```

Roteiro da apresentação: [`cadastro/README.md`](cadastro/README.md).
