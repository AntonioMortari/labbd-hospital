# LabBD — Sistema de Gestão Hospitalar e Telemedicina

Seminário final (P2) de Laboratório de Banco de Dados · Prof. Eduardo Freitas · apresentação em 27/11/2026

| Pasta | Tema | Banco | Responsáveis |
|---|---|---|---|
| [`cadastro/`](cadastro/) | Tema 1 · Cadastro de Pacientes, Equipe Médica e Agendamentos | PostgreSQL | Yuri e Antônio |

Cada tema fica numa pasta própria, com o seu `docker-compose.yml`. Os outros temas podem entrar aqui como
pastas irmãs (por exemplo `emergencia/` para o Tema 3), o que facilita montar o sistema completo.

## Tema 1 em um minuto

```bash
cd cadastro
docker compose up -d --build                 # sobe Postgres, 3 APIs e Nginx
# página de demo: http://localhost:8081  ·  API: http://localhost:8081/docs
docker compose --profile test run --rm tests # 66 testes
```

Roteiro completo da apresentação: [`cadastro/README.md`](cadastro/README.md).
