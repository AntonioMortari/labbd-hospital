const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PRIO = { 1: "Emergência", 2: "Muito urgente", 3: "Urgente", 4: "Pouco urgente", 5: "Não urgente" };
const PRIO_SELO = { 1: "recusado", 2: "aviso", 3: "aviso", 4: "agendado", 5: "" };
const REGRA = {
  "POST /patients": "ZADD na fila com pontuação prioridade × 10¹³ + horário: menor número primeiro, empate por chegada.",
  "POST /triage/call-next": "Script Lua: ZPOPMIN + marca 'chamado' + PUBLISH no painel, tudo numa operação só.",
  "POST /beds/allocate": "Script Lua: só passa de 'livre' para 'ocupado' quem chegar primeiro; ninguém mais entra no meio.",
  "POST /beds/release": "Script Lua: devolve o leito ao conjunto de livres e dá alta ao paciente.",
};
let ultimoRedis = "", scriptsCarregados = false;
let fila = [], leitos = [], chamados = [], internando = null, leitoSel = null, cadastro = [], eventos = 0, ultimo = "";

// ---- chamadas à API, sempre registradas nos bastidores
// ---- detalhes de cada ação: clicar (ou Enter) num cartão abre o que o banco executou
const detalhesPorId = new Map(); let seqDetalhe = 0;
function ligarDetalhes() {
  const abrir = (el) => { const ev = detalhesPorId.get(el?.dataset.ev); if (ev) Detalhes.abrir(ev); };
  $("log").addEventListener("click", (e) => abrir(e.target.closest("[data-ev]")));
  $("log").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { const c = e.target.closest("[data-ev]"); if (c) { e.preventDefault(); abrir(c); } } });
}

async function chamar(op, url, opts = {}) {
  const t0 = performance.now();
  let status = 0, corpo = {}, consultas = [];
  try {
    const r = await fetch(url, { ...opts, headers: { "Content-Type": "application/json", "X-Log": "1" } });
    status = r.status;
    corpo = await r.json().catch(() => ({}));
    consultas = await Detalhes.decodificar(r.headers.get("X-DB-Log")) || [];
  } catch { corpo = { detail: "API fora do ar" }; }
  const ok = status >= 200 && status < 300;
  registrar(op, ok, status, ok ? "" : (typeof corpo.detail === "string" ? corpo.detail : "Pedido recusado"), performance.now() - t0, { consultas, resposta: corpo });
  return { ok, status, corpo };
}
function registrar(op, ok, status, detalhe, ms, extra = {}) {
  const regra = REGRA[op.replace(/ \(.*\)$/, "").replace(/\/beds\/[^/]+\//, "/beds/")] || "";
  const ev = { titulo: op, op, ok, status, ms, regra: detalhe || regra, ...extra }, id = String(++seqDetalhe); detalhesPorId.set(id, ev);
  const li = document.createElement("li");
  li.className = `evento ${ok ? "ok" : "erro"} ${ev.consultas?.length ? "clicavel" : ""}`;
  if (ev.consultas?.length) { li.dataset.ev = id; li.tabIndex = 0; li.setAttribute("role", "button"); }
  li.innerHTML = `<div class="evento-topo"><span class="selo ${ok ? "gravado" : "recusado"}">${ok ? "executado" : "recusado"}</span><b>${status || "—"}</b><time>${new Date().toLocaleTimeString("pt-BR")}</time></div>
    <div><b>${esc(op)}</b> · ${Math.round(ms)} ms${detalhe ? ` · ${esc(detalhe)}` : ""}</div>${regra ? `<div class="evento-regra">${esc(regra)}</div>` : ""}${Detalhes.rodape(ev)}`;
  const log = $("log");
  log.querySelector(".vazio")?.remove();
  log.prepend(li);
  while (log.children.length > 15) log.lastChild.remove();
  $("conta-eventos").textContent = ++eventos;
}

// ---- desenho
const espera = (ms) => { const m = Math.max(0, Math.round((Date.now() - ms) / 60000)); return m < 1 ? "agora" : m < 60 ? `${m} min` : m < 1440 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`; };
const pessoas = () => [...new Map([...chamados, ...fila].map((p) => [p.id, p.name])).entries()];

function desenhar() {
  const livres = leitos.filter((l) => l.status === "livre").length;
  $("conta-fila").textContent = fila.length || "";
  $("conta-leitos").textContent = leitos.length ? `${livres} livres` : "";
  $("l-livres").textContent = `${livres} livres`;
  $("l-ocupados").textContent = `${leitos.length - livres} ocupados`;
  $("fila-vazia").hidden = fila.length > 0;
  $("tab-fila").hidden = fila.length === 0;
  $("chamar").disabled = fila.length === 0;
  $("tab-fila").querySelector("tbody").innerHTML = fila.map((p, i) => `<tr>
    <td>${i + 1}</td><td class="forte">${esc(p.name)}${p.paciente_id ? `<span class="sub">paciente do cadastro</span>` : ""}</td>
    <td><span class="selo ${PRIO_SELO[p.priority] ?? ""}">${p.priority} · ${PRIO[p.priority] || ""}</span></td><td>${espera(Number(p.arrived_at))}</td><td class="acoes"><button class="botao secundario sm" data-internar="${esc(p.id)}">Internar direto</button></td></tr>`).join("");
  $("bloco-chamados").hidden = chamados.length === 0;
  $("tab-chamados").querySelector("tbody").innerHTML = chamados.map((p) => `<tr><td class="forte">${esc(p.name)}${p.paciente_id ? `<span class="sub">paciente do cadastro</span>` : ""}</td>
    <td><span class="selo destaque">${esc(p.room)}</span></td><td class="acoes"><button class="botao primario sm" data-internar="${esc(p.id)}">Escolher leito</button></td></tr>`).join("");
  $("leitos").innerHTML = leitos.map((l) => `<button type="button" role="listitem" class="leito ${l.status === "livre" ? "" : "ocupado"}" data-id="${l.id}" aria-label="Leito ${l.id}, ${l.status}${l.name ? ", " + esc(l.name) : ""}">${l.id}</button>`).join("");
}

async function atualizar() {
  try {
    const [q, m, c] = await Promise.all(["/triage/queue?limit=100", "/beds/map", "/triage/called"].map((u) => fetch(u).then((r) => r.json())));
    const foto = JSON.stringify([q, m, c]);
    if (foto === ultimo) return;
    ultimo = foto; fila = q.next; leitos = m; chamados = c; desenhar();
  } catch { /* a próxima volta tenta de novo */ }
}
const refazer = () => { ultimo = ""; return atualizar(); };

// ---- abas, diálogos e bastidores
document.querySelectorAll("input[name=aba]").forEach((r) => r.addEventListener("change", () => {
  $("view-fila").hidden = r.value !== "fila" || !r.checked;
  $("view-leitos").hidden = r.value !== "leitos" || !r.checked;
  $("view-redis").hidden = r.value !== "redis" || !r.checked;
  if (r.value === "redis" && r.checked) { ultimoRedis = ""; carregarRedis(); }
}));
document.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
$("novo").addEventListener("click", () => { $("dlg-paciente").showModal(); $("nome").focus(); });
$("abrir-bastidores").addEventListener("click", () => { $("bastidores").hidden = !$("bastidores").hidden; });
$("fechar-bastidores").addEventListener("click", () => { $("bastidores").hidden = true; $("abrir-bastidores").focus(); });

$("form-paciente").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nome = $("nome").value.trim();
  const doCadastro = cadastro.find((p) => p.nome === nome);
  const prio = Number(document.querySelector("input[name=prio]:checked").value);
  const r = await chamar("POST /patients", "/patients", { method: "POST", body: JSON.stringify({ name: nome, priority: prio, ...(doCadastro ? { paciente_id: doCadastro.id } : {}) }) });
  if (r.ok) { $("nome").value = ""; $("dlg-paciente").close(); refazer(); }
});
$("chamar").addEventListener("click", async () => {
  const r = await chamar("POST /triage/call-next", `/triage/call-next?room=${encodeURIComponent($("sala").value)}`, { method: "POST" });
  if (!r.ok) return;
  $("aviso").textContent = `Chamado: ${r.corpo.name} → ${r.corpo.room}`;
  $("aviso").hidden = false;
  clearTimeout(window.__aviso); window.__aviso = setTimeout(() => { $("aviso").hidden = true; }, 8000);
  refazer();
});

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-internar]"); if (!b) return;
  const p = [...chamados, ...fila].find((x) => x.id === b.dataset.internar); if (!p) return;
  const livres = leitos.filter((l) => l.status === "livre");
  internando = p.id;
  $("internar-quem").textContent = p.name;
  $("internar-leito").innerHTML = livres.length ? livres.map((l) => `<option value="${l.id}">Leito ${l.id}</option>`).join("") : '<option value="">Nenhum leito livre</option>';
  $("confirmar-internar").disabled = livres.length === 0;
  $("dlg-internar").showModal();
});
$("confirmar-internar").addEventListener("click", async () => {
  const leito = $("internar-leito").value; if (!leito) return;
  $("dlg-internar").close();
  await chamar(`POST /beds/${leito}/allocate`, `/beds/${leito}/allocate?patient_id=${encodeURIComponent(internando)}`, { method: "POST" });
  refazer();
});

$("leitos").addEventListener("click", (e) => {
  const b = e.target.closest(".leito"); if (!b) return;
  leitoSel = b.dataset.id;
  const l = leitos.find((x) => x.id === leitoSel), livre = l.status === "livre", lista = pessoas();
  const grupo = (rotulo, itens) => itens.length ? `<optgroup label="${rotulo}">${itens.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</optgroup>` : "";
  $("t-leito").textContent = `Leito ${l.id} · ${livre ? "livre" : "ocupado"}`;
  $("leito-form").hidden = !livre; $("alocar").hidden = !livre;
  $("liberar").hidden = livre; $("leito-quem").hidden = livre;
  $("leito-quem").textContent = `Ocupado por ${l.name || l.patient}.`;
  $("leito-paciente").innerHTML = lista.length ? grupo("Chamados (já foram para a sala)", chamados) + grupo("Ainda na fila de espera", fila) : '<option value="">Ninguém na fila nem chamado</option>';
  $("alocar").disabled = lista.length === 0;
  $("dlg-leito").showModal();
});
$("alocar").addEventListener("click", async () => {
  const p = $("leito-paciente").value; if (!p) return;
  $("dlg-leito").close();
  await chamar(`POST /beds/${leitoSel}/allocate`, `/beds/${leitoSel}/allocate?patient_id=${encodeURIComponent(p)}`, { method: "POST" });
  refazer();
});
$("liberar").addEventListener("click", async () => {
  $("dlg-leito").close();
  await chamar(`POST /beds/${leitoSel}/release`, `/beds/${leitoSel}/release`, { method: "POST" });
  refazer();
});
$("corrida").addEventListener("click", async () => {
  const livre = leitos.find((l) => l.status === "livre"), duas = pessoas().slice(0, 2);
  $("bastidores").hidden = false;
  if (!livre || duas.length < 2) { registrar("Simular disputa", false, 0, "Precisa de um leito livre e de dois pacientes (na fila ou já chamados).", 0); return; }
  await Promise.all(duas.map(([id], i) =>
    chamar(`POST /beds/${livre.id}/allocate (recepcionista ${i + 1})`, `/beds/${livre.id}/allocate?patient_id=${id}`, { method: "POST" })));
  refazer();
});

// ---- tempo real (esta tela e o painel ouvem o mesmo canal)
function conectar() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/painel");
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    refazer();
  };
  ws.onclose = () => setTimeout(conectar, 2000);
}

// ---- cadastro do Tema 1 (só nome e id; quem manda no paciente é o Tema 1)
function urlCadastro() {
  const h = location.hostname, porta = location.port ? ":" + location.port : "";
  return h.startsWith("triagem.") ? `${location.protocol}//cadastro.${h.slice(8)}${porta}` : `${location.protocol}//cadastro.localhost:8000`;
}
async function carregarCadastro() {
  try {
    cadastro = await (await fetch(`${urlCadastro()}/pacientes`)).json();
    $("cadastro").innerHTML = cadastro.map((p) => `<option value="${esc(p.nome)}"></option>`).join("");
    $("dica-cadastro").textContent = "Pacientes do cadastro (Tema 1) aparecem como sugestão. Quem não está lá entra só pelo nome.";
  } catch { $("dica-cadastro").textContent = "Cadastro do Tema 1 indisponível: dá para registrar só pelo nome."; }
}

$("prio").innerHTML = [1, 2, 3, 4, 5].map((n) => `<label><input type="radio" name="prio" value="${n}" ${n === 3 ? "checked" : ""}><span>${n}<small>${PRIO[n]}</small></span></label>`).join("");
$("sala").innerHTML = [1, 2, 3, 4].map((n) => `<option>Sala ${n}</option>`).join("");
carregarCadastro(); atualizar(); conectar(); setInterval(atualizar, 3000);

// ---- Redis por dentro (só leitura): estruturas e scripts Lua
const PORQUE = {
  "triage:queue": ["sorted set", "Fila com prioridade. Cada paciente entra com uma pontuação = prioridade × 10¹³ + horário de chegada (em ms): quem tem menor pontuação sai primeiro, e quem chegou antes desempata. Tirar o próximo é ZPOPMIN, O(log N)."],
  "patient:*": ["hash", "Um hash por paciente, com nome, prioridade, status (aguardando, chamado, internado, alta), sala e leito. Acesso direto pela chave, sem varrer nada."],
  "bed:*": ["hash", "Um hash por leito com o status (livre ou ocupado) e o paciente. É o estado que o script de alocar lê e grava de forma atômica."],
  "beds:free": ["set", "Conjunto dos leitos livres: saber quantos estão livres é SCARD, O(1). O painel usa esse número."],
  "beds:occupied": ["set", "Conjunto dos leitos ocupados. O script move o leito entre os dois conjuntos (SMOVE) junto com a mudança de status."],
  "beds:init": ["hash", "Marca quais leitos já foram criados. Serve para várias réplicas da API semearem os leitos ao mesmo tempo sem duplicar."],
  "panel:recent": ["list", "Histórico das últimas 20 chamadas. O painel de TV lê esta lista ao conectar e mostra o que já foi chamado."],
};
const SCRIPT_TXT = {
  CALL_NEXT: ["Chamar o próximo", "Tira o paciente de menor pontuação da fila, marca como chamado, guarda no histórico e avisa o painel, tudo numa execução só. Dois recepcionistas chamando ao mesmo tempo nunca recebem o mesmo paciente."],
  ALLOCATE_BED: ["Alocar leito", "Confere se o leito está livre e o ocupa na mesma execução. O Redis roda o script inteiro sem intercalar outros comandos, então só um dos dois recepcionistas passa; o outro recebe 0 (leito ocupado). Retornos: 1 ok, 0 ocupado, -1 leito inexistente, -2 paciente inexistente, -3 paciente já tem leito."],
  RELEASE_BED: ["Liberar leito", "Devolve o leito ao conjunto de livres, tira o paciente do leito e dá alta, de uma vez."],
};
const fmtPontos = (n) => { const prio = Math.floor(n / 1e13), ms = n - prio * 1e13; return `prioridade ${prio} · chegou ${new Date(ms).toLocaleTimeString("pt-BR")}`; };

function conteudoHtml(g, a) {
  const c = a.conteudo;
  if (g.tipo === "hash") return `<dl class="campos">${Object.entries(c).slice(0, 24).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  if (g.tipo === "zset") return c.length ? `<dl class="campos">${c.map((m) => `<dt>${esc(m.membro)}</dt><dd>${esc(m.pontuacao)} <span class="dica">(${fmtPontos(m.pontuacao)})</span></dd>`).join("")}</dl>` : '<p class="mono-bloco dica">vazio</p>';
  if (g.tipo === "set") return `<div class="fichas">${c.map((m) => `<span class="ficha">${esc(m)}</span>`).join("")}</div>`;
  if (g.tipo === "list") return `<pre class="mono-bloco">${esc(c.slice(0, 6).join("\n"))}</pre>`;
  return `<pre class="mono-bloco">${esc(c)}</pre>`;
}

async function carregarRedis() {
  if ($("view-redis").hidden) return;
  try {
    const d = await (await fetch("/redis/estruturas")).json();
    const foto = JSON.stringify(d);
    if (foto !== ultimoRedis) {
      ultimoRedis = foto;
      const sv = d.servidor;
      $("redis-resumo").innerHTML = [["Redis", sv.versao], ["Memória", sv.memoria], ["Clientes conectados", sv.clientes], ["Painéis ouvindo", `${d.canal.inscritos} em ${d.canal.nome}`]]
        .map(([a, b]) => `<div><dt>${a}</dt><dd>${esc(b)}</dd></div>`).join("");
      const ordem = Object.keys(PORQUE);
      const grupos = [...d.grupos].sort((a, b) => (ordem.indexOf(a.grupo) + 1 || 99) - (ordem.indexOf(b.grupo) + 1 || 99))
        .map((g) => ({ ...g, amostra: g.amostra.slice(0, g.tipo === "hash" ? 3 : 8) }));
      $("redis-grupos").innerHTML = grupos.map((g) => {
        const [tipo, texto] = PORQUE[g.grupo] || [g.tipo, ""];
        return `<article class="cartao grupo"><div class="grupo-topo"><code>${esc(g.grupo)}</code><span class="selo destaque sem-ponto">${esc(tipo)}</span>
          <span class="n">${g.chaves} ${g.chaves === 1 ? "chave" : "chaves"}${g.chaves > g.amostra.length ? ` · mostrando ${g.amostra.length}` : ""}</span></div>
          ${texto ? `<p class="porque">${esc(texto)}</p>` : ""}
          ${g.amostra.map((a) => `<div class="amostra"><div class="chave-linha"><b>${esc(a.chave)}</b><span>${a.tamanho} itens</span><span>${a.ttl === null ? "sem expiração" : "expira em " + a.ttl + " s"}</span></div>${conteudoHtml(g, a)}</div>`).join("")}</article>`;
      }).join("") || '<div class="cartao estado-vazio"><strong>O Redis está vazio</strong></div>';
    }
    if (!scriptsCarregados) {
      const sc = await (await fetch("/redis/scripts")).json();
      $("redis-scripts").className = "cartao scripts";
      $("redis-scripts").innerHTML = sc.map((x) => `<details><summary><span class="selo aviso sem-ponto">Lua</span>${esc(SCRIPT_TXT[x.nome]?.[0] || x.nome)} <code>${esc(x.nome)}</code></summary><p class="explica">${esc(SCRIPT_TXT[x.nome]?.[1] || "")}</p><pre>${esc(x.codigo)}</pre></details>`).join("");
      scriptsCarregados = true;
    }
  } catch { /* tenta de novo na próxima volta */ }
}
setInterval(carregarRedis, 3000);
ligarDetalhes();
