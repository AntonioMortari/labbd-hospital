"""500 recepcionistas tentando agendar o MESMO médico no MESMO horário ao mesmo tempo.

Os pedidos passam pelo Nginx e se espalham pelas 3 réplicas da API.
Quem garante que só um vence é o PostgreSQL (exclusion constraint), não a API.
"""
import asyncio
import os
import random
import sys
from datetime import date, timedelta

import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8081")
N = int(os.getenv("N", "500"))


async def main() -> int:
    limits = httpx.Limits(max_connections=300)
    async with httpx.AsyncClient(base_url=BASE, timeout=60, limits=limits) as c:
        medico = (await c.get("/medicos")).json()[0]
        amanha = date.today() + timedelta(days=1)
        inicio, fim = f"{amanha}T07:00:00", f"{amanha}T07:30:00"

        # pacientes diferentes, para que só a regra do MÉDICO esteja em jogo
        prefixo = random.randint(100, 999)
        pacientes = []
        for i in range(N):
            r = await c.post("/pacientes", json={"nome": f"Corrida {i}", "cpf": f"{prefixo}{i:08d}",
                                                 "data_nascimento": "1990-01-01"})
            r.raise_for_status()
            pacientes.append(r.json()["id"])

        print(f"[RACE] {N} agendamentos simultâneos: {medico['nome']}, {amanha:%d/%m/%Y} 07:00-07:30")
        respostas = await asyncio.gather(*[
            c.post("/agendamentos", json={"paciente_id": p, "medico_id": medico["id"], "tipo": "consulta",
                                          "inicio": inicio, "fim": fim})
            for p in pacientes])

        sucessos = [r for r in respostas if r.status_code == 201]
        conflitos = sum(1 for r in respostas if r.status_code == 409)
        outros = len(respostas) - len(sucessos) - conflitos
        print(f"[RACE] sucessos={len(sucessos)} (esperado=1) conflitos={conflitos}"
              + (f" outros={outros}" if outros else ""))

        # libera o horário para a demo poder ser repetida
        for r in sucessos:
            await c.post(f"/agendamentos/{r.json()['id']}/cancelar")
        return 0 if len(sucessos) == 1 and outros == 0 else 1


sys.exit(asyncio.run(main()))
