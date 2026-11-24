#!/usr/bin/env python3
"""Sistema completo: gera o gateway a partir de modulos.json, sobe/para os módulos e mostra quem está no ar.

Uso (a partir da raiz do repositório):
  python3 integracao/sistema.py gerar             só escreve integracao/nginx.conf
  python3 integracao/sistema.py subir [id ...]    sobe os módulos que já têm pasta (ou só os ids dados) e o gateway
  python3 integracao/sistema.py parar             derruba módulos e gateway (não apaga volumes)
  python3 integracao/sistema.py status            mostra quem responde em /health

Para entrar no sistema, um módulo só precisa estar listado em modulos.json: veja integracao/CONTRATO.md.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AQUI = RAIZ / "integracao"
REGISTRO = json.loads((RAIZ / "modulos.json").read_text(encoding="utf-8"))
MODULOS = REGISTRO["modulos"]
PORTA = str(REGISTRO["gateway"]["porta"])

BASE = """\
# GERADO por integracao/sistema.py a partir de modulos.json. Não edite à mão: rode `python3 integracao/sistema.py gerar`.
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  map $http_upgrade $conexao { default upgrade; '' close; }

  # página inicial (hub) em http://localhost
  server {
    listen 80 default_server;
    server_name _;
    root /usr/share/nginx/html;
    location /kit/ { alias /usr/share/nginx/kit/; add_header Cache-Control no-cache; }
    location = /modulos.json { alias /etc/nginx/modulos.json; add_header Cache-Control no-store; }
%(saude)s    location / { add_header Cache-Control no-cache; try_files $uri /index.html; }
  }
%(servidores)s}
"""

# /_health/<id>: o hub checa cada módulo pela mesma origem dele (sem CORS)
SAUDE = """\
    location = /_health/%(id)s {
      proxy_pass http://host.docker.internal:%(porta)s/health;
      proxy_connect_timeout 1s;
      proxy_read_timeout 2s;
    }
"""

# um endereço por módulo: o módulo continua servido na raiz "/", sem mudar nada no código dele
SERVIDOR = """
  server {
    listen 80;
    server_name %(id)s.localhost;
    location / {
      proxy_pass http://host.docker.internal:%(porta)s;
      proxy_http_version 1.1;
      proxy_buffer_size 32k;
      proxy_buffers 8 32k;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $conexao;
      proxy_connect_timeout 2s;
      error_page 502 503 504 = @fora;
    }
    location @fora {
      default_type text/html;
      return 503 "<!doctype html><meta charset=utf-8><title>%(nome)s</title><body style='font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 24px;color:#0F172A'><h1>Tema %(tema)s fora do ar</h1><p>O módulo <b>%(nome)s</b> não está respondendo na porta %(porta)s.</p><p>Suba o módulo (pasta <code>%(pasta)s/</code>) ou rode <code>python3 integracao/sistema.py subir %(id)s</code> e recarregue a página.</p></body>";
    }
  }
"""


def gerar():
    conf = BASE % {
        "saude": "".join(SAUDE % m for m in MODULOS),
        "servidores": "".join(SERVIDOR % m for m in MODULOS),
    }
    (AQUI / "nginx.conf").write_text(conf, encoding="utf-8")
    print(f"nginx.conf gerado com {len(MODULOS)} módulos")


def compose(arquivo, *args, **kw):
    ambiente = {**os.environ, "GATEWAY_PORTA": PORTA}
    return subprocess.run(["docker", "compose", "-f", str(arquivo), *args], env=ambiente, **kw)


def com_pasta(ids=()):
    for m in MODULOS:
        if ids and m["id"] not in ids:
            continue
        yield m, RAIZ / m["pasta"] / "docker-compose.yml"


def subir(ids):
    gerar()
    for m, arq in com_pasta(ids):
        if not arq.exists():
            print(f"- {m['id']}: a pasta '{m['pasta']}/' ainda não tem docker-compose.yml, pulando")
            continue
        print(f"- {m['id']}: subindo...")
        compose(arq, "up", "-d", "--build")
    compose(AQUI / "docker-compose.yml", "up", "-d")
    compose(AQUI / "docker-compose.yml", "exec", "-T", "gateway", "nginx", "-s", "reload", capture_output=True)
    print(f"\nHub: http://localhost:{PORTA}")
    for m in MODULOS:
        print(f"  Tema {m['tema']}: http://{m['id']}.localhost:{PORTA}")


def parar():
    for m, arq in com_pasta():
        if arq.exists():
            print(f"- {m['id']}: parando...")
            compose(arq, "down")
    compose(AQUI / "docker-compose.yml", "down")


def status():
    for m in MODULOS:
        try:
            with urllib.request.urlopen(f"http://localhost:{m['porta']}/health", timeout=1.5) as r:
                ok = r.status == 200
        except Exception:
            ok = False
        print(f"Tema {m['tema']}  {m['id']:<11} porta {m['porta']}  {'no ar' if ok else 'fora do ar'}")


if __name__ == "__main__":
    comando, *resto = sys.argv[1:] or ["status"]
    {"gerar": gerar, "subir": lambda: subir(resto), "parar": parar, "status": status}.get(
        comando, lambda: sys.exit(__doc__))()
