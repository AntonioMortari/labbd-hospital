"use strict";

// ---------------------------------------------------------------- regras do banco
// nome da regra no PostgreSQL → [tipo, explicação]
const REGRAS = {
  sem_conflito_medico: ["EXCLUDE", "o médico já tem atendimento nesse intervalo"],
  sem_conflito_paciente: ["EXCLUDE", "o paciente já tem atendimento nesse intervalo"],
  paciente_cpf_key: ["UNIQUE", "esse CPF já está cadastrado"],
  paciente_cpf_check: ["CHECK", "o CPF precisa ter 11 dígitos"],
  plano_completo: ["CHECK", "paciente com plano precisa de carteirinha e validade (ou nenhum dos três)"],
  paciente_data_nascimento_check: ["CHECK", "a data de nascimento não pode estar no futuro"],
  paciente_plano_id_fkey: ["FOREIGN KEY", "o plano escolhido não existe"],
  valor_so_em_cirurgia: ["CHECK", "só cirurgia tem valor próprio, e toda cirurgia precisa dele"],
  agendamento_valor_cirurgia_check: ["CHECK", "o valor da cirurgia precisa ser maior que zero"],
  agendamento_periodo_check: ["CHECK", "o horário de fim precisa ser depois do início"],
  agendamento_medico_id_fkey: ["FOREIGN KEY", "o médico não existe"],
  agendamento_paciente_id_fkey: ["FOREIGN KEY", "o paciente não existe"],
  realizar_atendimento: ["PROCEDURE", "a transação foi desfeita (rollback): nada foi gravado"],
  trg_transicao_status: ["TRIGGER", "realizado e cancelado são estados finais"],
};
// estas devolvem a mensagem crua do Postgres (em inglês): o título vira a explicação em português
const DECLARATIVAS = ["UNIQUE", "CHECK", "FOREIGN KEY"];

// ---------------------------------------------------------------- utilidades
const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => [...raiz.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "America/Sao_Paulo";
const brl = (v) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const hora = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
const horaSeg = (d) => d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: TZ });
const diaLongo = (iso) => new Date(iso).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", timeZone: TZ });
const diaCurto = (iso) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", timeZone: TZ });
const quando = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: TZ });
const dataBR = (ymd) => ymd ? ymd.split("-").reverse().join("/") : "—";
const hojeISO = (desloc = 0) => new Date(Date.now() + desloc * 864e5).toLocaleDateString("en-CA", { timeZone: TZ });
const cpfFmt = (c) => /^\d{11}$/.test(c || "") ? `${c.slice(0, 3)}.${c.slice(3, 6)}.${c.slice(6, 9)}-${c.slice(9)}` : esc(c);
const maiuscula = (t) => t.charAt(0).toUpperCase() + t.slice(1) + ".";

const estado = {
  pacientes: [], medicos: [], planos: {}, agendamentos: [], faturas: [], auditoria: [], eventos: [],
  vistos: new Set(), primeira: true, view: "agenda",
  emAndamento: new Set(),            // ids de agendamento com Realizar/Cancelar em curso (evita clique duplo)
  ultimo: { ag: "", fat: "", aud: "" }, // última resposta de cada lista: só redesenha quando muda
  online: true, carregando: false,
};

async function api(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: { "X-Usuario": $("#usuario").value } };
  if (metodo !== "GET") opcoes.headers["X-Log"] = "1";  // pede à API o SQL que o banco executou
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  try {
    const t0 = performance.now();
    const r = await fetch(caminho, opcoes);
    const dados = await r.json().catch(() => ({}));
    if (metodo !== "GET") {
      const consultas = await Detalhes.decodificar(r.headers.get("X-DB-Log"));
      estado.ultimoLog = { op: `${metodo} ${caminho}`, status: r.status, ms: performance.now() - t0, consultas: consultas || [], resposta: dados };
    }
    return { ok: r.ok, status: r.status, dados };
  } catch {
    return { ok: false, status: 0, dados: { detail: "Sem conexão com a API (localhost:8081)." } };
  }
}

// ---------------------------------------------------------------- navegação
const VIEWS = ["agenda", "pacientes", "faturas", "auditoria", "banco"];

function irPara(view) {
  if (!VIEWS.includes(view)) view = "agenda";
  estado.view = view;
  $$(".view").forEach((s) => (s.hidden = s.id !== `view-${view}`));
  $$(".nav-item").forEach((a) => {
    const ativo = a.dataset.view === view;
    a.classList.toggle("ativo", ativo);
    if (ativo) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  document.title = `${$(`#view-${view}`).dataset.titulo} · Recepção`;
}
window.addEventListener("hashchange", () => irPara(location.hash.replace("#/", "")));

// ---------------------------------------------------------------- telas
function vazio(titulo, texto, acao) {
  return `<div class="estado-vazio"><strong>${titulo}</strong><span>${texto}</span>${acao || ""}</div>`;
}

// Troca o HTML de uma área sem derrubar o foco do teclado (o botão focado é achado de novo pelo data-*).
function trocar(seletor, html) {
  const alvo = $(seletor), foco = document.activeElement;
  const chave = alvo.contains(foco) ? ["realizar", "cancelar", "abrir"].find((k) => foco.dataset?.[k] !== undefined) : null;
  const valor = chave ? foco.dataset[chave] : null;
  alvo.innerHTML = html;
  if (chave) alvo.querySelector(`[data-${chave}="${valor}"]`)?.focus();
}

const render = {
  agenda() {
    const filtro = $("#filtro-medico").value;
    const desde = new Date(`${hojeISO()}T00:00:00-03:00`);
    const futuros = estado.agendamentos.filter((a) => new Date(a.inicio) >= desde);
    const lista = futuros.filter((a) => !filtro || String(a.medico_id) === filtro).slice(0, 60);
    $("#conta-agenda").textContent = futuros.filter((a) => a.status === "agendado").length || "";
    if (!lista.length) {
      $("#agenda").innerHTML = vazio(filtro ? "Nenhum atendimento para esse médico" : "Agenda vazia",
        "Não há atendimentos a partir de hoje.",
        '<button class="botao primario" type="button" data-abrir="agendamento">Novo agendamento</button>');
      return;
    }
    let linhas = "", dia = "";
    for (const a of lista) {
      const d = diaLongo(a.inicio);
      if (d !== dia) { linhas += `<tr class="grupo"><td colspan="4">${esc(d.charAt(0).toUpperCase() + d.slice(1))}</td></tr>`; dia = d; }
      const chave = `ag:${a.id}:${a.status}`;
      const novo = !estado.primeira && !estado.vistos.has(chave);
      const tipo = a.tipo === "cirurgia"
        ? ` <span class="selo aviso sem-ponto">Cirurgia · ${brl(a.valor_cirurgia)}</span>` : "";
      const ocupado = estado.emAndamento.has(String(a.id)) ? " disabled" : "";
      const acoes = a.status === "agendado"
        ? `<div><button class="botao secundario sm" type="button" data-realizar="${a.id}" aria-label="Realizar atendimento de ${esc(a.paciente)}"${ocupado}>Realizar</button><button class="botao fantasma sm perigo" type="button" data-cancelar="${a.id}" aria-label="Cancelar agendamento de ${esc(a.paciente)}"${ocupado}>Cancelar</button></div>` : "";
      linhas += `<tr${novo ? ' class="novo"' : ""}>
        <td class="hora">${hora(a.inicio)}–${hora(a.fim)}</td>
        <td><span class="forte">${esc(a.paciente)}</span>${tipo}<span class="sub">${esc(a.medico)} · ${a.tipo === "cirurgia" ? "cirurgia" : "consulta"}</span></td>
        <td><span class="selo ${esc(a.status)}">${esc(a.status.charAt(0).toUpperCase() + a.status.slice(1))}</span></td>
        <td class="acoes">${acoes}</td></tr>`;
    }
    trocar("#agenda", `<table class="tabela"><thead><tr><th>Horário</th><th>Paciente</th><th>Status</th><th><span class="sr">Ações</span></th></tr></thead><tbody>${linhas}</tbody></table>`);
    estado.agendamentos.forEach((a) => estado.vistos.add(`ag:${a.id}:${a.status}`));
  },

  pacientes() {
    const lista = [...estado.pacientes].sort((a, b) => b.id - a.id);
    $("#conta-pacientes").textContent = lista.length || "";
    if (!lista.length) {
      $("#pacientes-tabela").innerHTML = vazio("Nenhum paciente", "Cadastre o primeiro paciente.",
        '<button class="botao primario" type="button" data-abrir="paciente">Novo paciente</button>');
      return;
    }
    const hoje = hojeISO();
    $("#pacientes-tabela").innerHTML = `<table class="tabela"><thead><tr><th>Paciente</th><th>CPF</th><th>Nascimento</th><th>Plano</th><th>Validade</th></tr></thead><tbody>${
      lista.map((p) => {
        const plano = p.plano_id ? estado.planos[p.plano_id] : null;
        const vencido = p.validade_carteirinha && p.validade_carteirinha < hoje;
        const novo = !estado.primeira && !estado.vistos.has(`pac:${p.id}`);
        return `<tr${novo ? ' class="novo"' : ""}>
          <td><span class="forte">${esc(p.nome)}</span>${p.telefone ? `<span class="sub">${esc(p.telefone)}</span>` : ""}</td>
          <td data-rotulo="CPF">${cpfFmt(p.cpf)}</td>
          <td data-rotulo="Nascimento">${dataBR(p.data_nascimento)}</td>
          <td data-rotulo="Plano">${plano ? `<span class="selo destaque sem-ponto">${esc(plano)}</span>` : '<span class="selo sem-ponto">Particular</span>'}</td>
          <td data-rotulo="Validade">${p.validade_carteirinha ? `${dataBR(p.validade_carteirinha)}${vencido ? ' <span class="selo vencido">Vencido</span>' : ""}` : "—"}</td></tr>`;
      }).join("")}</tbody></table>`;
    estado.pacientes.forEach((p) => estado.vistos.add(`pac:${p.id}`));
  },

  faturas() {
    const f = estado.faturas;
    $("#conta-faturas").textContent = f.length || "";
    const soma = (k) => f.reduce((t, x) => t + Number(x[k]), 0);
    $("#resumo-faturas").innerHTML = `
      <div><dt>Faturas emitidas</dt><dd>${f.length}</dd></div>
      <div><dt>Total</dt><dd>${brl(soma("valor_total"))}</dd></div>
      <div><dt>Pago pelos convênios</dt><dd>${brl(soma("valor_convenio"))}</dd></div>
      <div><dt>Pago pelos pacientes</dt><dd>${brl(soma("valor_paciente"))}</dd></div>`;
    if (!f.length) {
      $("#faturas").innerHTML = vazio("Nenhuma fatura ainda", "Realize um atendimento na Agenda para emitir a primeira.",
        '<a class="botao secundario" href="#/agenda">Ir para a Agenda</a>');
      return;
    }
    $("#faturas").innerHTML = `<table class="tabela"><thead><tr><th>Fatura</th><th>Paciente</th><th>Emitida em</th><th class="num">Total</th><th class="num">Convênio</th><th class="num">Paciente</th></tr></thead><tbody>${
      f.map((x) => {
        const novo = !estado.primeira && !estado.vistos.has(`fat:${x.id}`);
        return `<tr${novo ? ' class="novo"' : ""}>
          <td class="forte">#${x.id}</td>
          <td><span class="forte">${esc(x.paciente)}</span><span class="sub">${esc(x.tipo === "cirurgia" ? "Cirurgia" : "Consulta")}</span></td>
          <td data-rotulo="Emitida em">${quando(x.emitida_em)}</td>
          <td class="num forte" data-rotulo="Total">${brl(x.valor_total)}</td>
          <td class="num" data-rotulo="Convênio">${brl(x.valor_convenio)}</td>
          <td class="num" data-rotulo="Paciente">${brl(x.valor_paciente)}</td></tr>`;
      }).join("")}</tbody></table>`;
    f.forEach((x) => estado.vistos.add(`fat:${x.id}`));
  },

  auditoria() {
    const a = estado.auditoria;
    if (!a.length) { $("#auditoria").innerHTML = vazio("Sem registros", "Nenhuma alteração auditada ainda."); return; }
    const cls = { INSERT: "gravado", UPDATE: "aviso", DELETE: "recusado" };
    $("#auditoria").innerHTML = `<table class="tabela"><thead><tr><th>Quando</th><th>Atendente</th><th>Registro</th><th>Operação</th><th>O que mudou</th></tr></thead><tbody>${
      a.map((x) => {
        const novo = !estado.primeira && !estado.vistos.has(`aud:${x.id}`);
        return `<tr${novo ? ' class="novo"' : ""}>
          <td class="hora" data-rotulo="Quando">${quando(x.em)}</td>
          <td data-rotulo="Atendente">${esc(x.usuario)}</td>
          <td data-rotulo="Registro">${esc(x.tabela)} #${x.registro_id}</td>
          <td><span class="selo ${cls[x.operacao] || ""} sem-ponto">${esc(x.operacao)}</span></td>
          <td>${mudancas(x)}</td></tr>`;
      }).join("")}</tbody></table>`;
    a.forEach((x) => estado.vistos.add(`aud:${x.id}`));
  },
};

function mudancas(a) {
  if (a.operacao === "INSERT") return `<div class="mudanca">Cadastro novo: <b>${esc(a.dados_novos?.nome ?? "")}</b></div>`;
  if (a.operacao === "DELETE") return `<div class="mudanca">Registro apagado: <b>${esc(a.dados_antigos?.nome ?? "")}</b></div>`;
  const antes = a.dados_antigos || {}, depois = a.dados_novos || {};
  return Object.keys(depois).filter((k) => JSON.stringify(antes[k]) !== JSON.stringify(depois[k]))
    .map((k) => `<div class="mudanca">${esc(k)}: ${esc(antes[k] ?? "—")} → <b>${esc(depois[k] ?? "—")}</b></div>`).join("");
}

// ---------------------------------------------------------------- bastidores do banco
const bastidores = {
  registrar(ev) {
    estado.eventos.unshift({ ...ev, regraHtml: true, ...(estado.ultimoLog || {}), em: new Date() });
    estado.ultimoLog = null;
    estado.eventos.length = Math.min(estado.eventos.length, 30);
    this.desenhar();
  },
  desenhar() {
    $("#eventos-vazio").hidden = estado.eventos.length > 0;
    $("#conta-eventos").textContent = estado.eventos.length || "";
    $("#eventos").innerHTML = estado.eventos.map((e) => `
      <li class="evento ${e.ok ? "ok" : "erro"} ${e.consultas?.length ? "clicavel" : ""}" ${e.consultas?.length ? `data-evento="${estado.eventos.indexOf(e)}" tabindex="0" role="button" aria-label="Ver o SQL executado"` : ""}>
        <div class="evento-topo">
          <span class="selo ${e.ok ? "gravado" : "recusado"}">${e.ok ? "Gravado" : "Recusado"}</span>
          <span class="evento-codigo">${e.status || "—"}</span>
          <span class="evento-hora">${horaSeg(e.em)}</span>
        </div>
        <p class="evento-titulo">${esc(e.titulo)}</p>
        ${e.regra ? `<p class="evento-regra">${e.regra}</p>` : ""}
        ${e.sqlstate ? `<p class="evento-sqlstate">SQLSTATE ${esc(e.sqlstate)}</p>` : ""}
        ${Detalhes.rodape(e)}
      </li>`).join("");
  },
  abrir() { $("#bastidores").classList.add("aberto"); },
  fechar() { $("#bastidores").classList.remove("aberto"); },
};

// Traduz a resposta de erro da API num evento: título em português, regra e SQLSTATE do Postgres.
function eventoDeErro(r) {
  const { detail, sqlstate, regra } = r.dados || {};
  const info = regra && REGRAS[regra];
  let titulo = Array.isArray(detail) ? "Preencha os campos obrigatórios com valores válidos." : (detail || "Operação recusada.");
  let linha = "";
  if (info && DECLARATIVAS.includes(info[0])) {
    titulo = maiuscula(info[1]);
    linha = `<span class="tipo">${info[0]}</span> <code>${esc(regra)}</code>`;
  } else if (info) {
    linha = `<span class="tipo">${info[0]}</span> <code>${esc(regra)}</code>: ${esc(info[1])}`;
  } else if (regra) {
    linha = `Regra <code>${esc(regra)}</code>`;
  } else if (sqlstate && sqlstate.startsWith("22")) {
    titulo = "Dado inválido: confira as datas e os horários (o fim precisa ser depois do início).";
    linha = `PostgreSQL: ${esc(detail)}`;
  } else if (r.status === 0) {
    linha = "Confira se o Docker está rodando.";
  }
  return { ok: false, status: r.status, titulo, regra: linha, sqlstate };
}

// ---------------------------------------------------------------- gavetas
const gaveta = {
  atual: null,
  abrir(nome) {
    const el = $(`#gaveta-${nome}`);
    const form = $("form", el);
    if (nome === "agendamento") {
      form.dia.value ||= hojeISO(1);
      form.inicio.value ||= "16:00";
      form.fim.value ||= "16:30";
    }
    this.erro(el, null);
    if (!this.atual) this.foco = document.activeElement;   // para devolver o foco ao fechar (só na 1ª abertura)
    $(".app").inert = true;               // a página de trás não recebe Tab nem clique
    el.hidden = false;
    $("#fundo-gaveta").hidden = false;
    this.atual = el;
    $(".controle", el).focus();
  },
  fechar() {
    if (!this.atual) return;
    this.atual.hidden = true;
    $("#fundo-gaveta").hidden = true;
    this.atual = null;
    $(".app").inert = false;
    const volta = this.foco?.isConnected && !this.foco.disabled ? this.foco : $$("[data-abrir]").find((b) => b.offsetParent);
    this.foco = null;
    volta?.focus();
  },
  erro(el, ev) {
    const alerta = $(".alerta", el);
    alerta.hidden = !ev;
    alerta.innerHTML = ev ? `<strong>${esc(ev.titulo)}</strong>${ev.regra ? `<span>${ev.regra}${ev.sqlstate ? ` · SQLSTATE ${esc(ev.sqlstate)}` : ""}</span>` : ""}` : "";
  },
};

document.addEventListener("click", (e) => {
  const abrir = e.target.closest("[data-abrir]");
  if (abrir) gaveta.abrir(abrir.dataset.abrir);
  if (e.target.closest("[data-fechar]") || e.target.id === "fundo-gaveta") gaveta.fechar();
  const cartao = e.target.closest("[data-evento]");
  if (cartao) Detalhes.abrir(estado.eventos[Number(cartao.dataset.evento)]);
  if (e.target.closest("#abrir-bastidores")) bastidores.abrir();
  if (e.target.closest(".fechar-bastidores")) bastidores.fechar();
});
document.addEventListener("keydown", (e) => {
  const cartao = e.target.closest?.("[data-evento]");
  if (cartao && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); Detalhes.abrir(estado.eventos[Number(cartao.dataset.evento)]); return; }
  if (e.key === "Escape" && !document.getElementById("dlg-detalhe")?.open) { gaveta.fechar(); bastidores.fechar(); }
});

$$("#form-agendamento [name=tipo]").forEach((r) => r.addEventListener("change", () => {
  $("#campo-valor").hidden = $("#form-agendamento").tipo.value !== "cirurgia";
}));

async function enviar(form, executar) {
  const botao = $("button[type=submit]", form);
  const texto = botao.textContent;
  botao.disabled = true;
  botao.textContent = "Salvando…";
  try { await executar(); } finally { botao.disabled = false; botao.textContent = texto; }
}

$("#form-paciente").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target;
  enviar(form, async () => {
    const corpo = Object.fromEntries([...new FormData(form)].map(([k, v]) => [k, v === "" ? null : v]));
    if (corpo.plano_id) corpo.plano_id = Number(corpo.plano_id);
    const r = await api("POST", "/pacientes", corpo);
    if (!r.ok) {
      const e = eventoDeErro(r);
      gaveta.erro($("#gaveta-paciente"), e);
      bastidores.registrar(e);
      return;
    }
    const aud = await api("GET", "/auditoria?limit=5");
    const registrou = aud.ok && aud.dados.some((a) => a.tabela === "paciente" && a.registro_id === r.dados.id && a.operacao === "INSERT");
    bastidores.registrar({
      ok: true, status: r.status, titulo: `${r.dados.nome} cadastrado (paciente #${r.dados.id}).`,
      regra: registrou ? '<span class="tipo">TRIGGER</span> <code>fn_auditoria</code> registrou o INSERT na auditoria.' : "INSERT em <code>paciente</code> confirmado.",
    });
    form.reset();
    gaveta.fechar();
    location.hash = "#/pacientes";
    await carregarCadastros();
    atualizar();
  });
});

$("#form-agendamento").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const form = ev.target;
  enviar(form, async () => {
    const tipo = form.tipo.value;
    const corpo = {
      paciente_id: Number(form.paciente_id.value), medico_id: Number(form.medico_id.value), tipo,
      inicio: `${form.dia.value}T${form.inicio.value}`, fim: `${form.dia.value}T${form.fim.value}`,
      valor_cirurgia: tipo === "cirurgia" && form.valor_cirurgia.value ? Number(form.valor_cirurgia.value) : null,
    };
    const r = await api("POST", "/agendamentos", corpo);
    if (!r.ok) {
      const e = eventoDeErro(r);
      gaveta.erro($("#gaveta-agendamento"), e);
      bastidores.registrar(e);
      return;
    }
    bastidores.registrar({
      ok: true, status: r.status,
      titulo: `Agendado: ${diaCurto(r.dados.inicio)}, ${hora(r.dados.inicio)}–${hora(r.dados.fim)} (agendamento #${r.dados.id}).`,
      regra: '<span class="tipo">EXCLUDE</span> <code>sem_conflito_medico</code> e <code>sem_conflito_paciente</code>: nenhum horário sobreposto.',
    });
    gaveta.fechar();
    location.hash = "#/agenda";
    atualizar();
  });
});

$("#agenda").addEventListener("click", async (e) => {
  const botao = e.target.closest("button[data-realizar], button[data-cancelar]");
  if (!botao) return;
  const id = botao.dataset.realizar || botao.dataset.cancelar;
  // Cancelar é irreversível (cancelado é estado final): o primeiro clique só pede confirmação.
  if (botao.dataset.cancelar && !botao.classList.contains("armado")) {
    botao.classList.add("armado");
    botao.textContent = "Confirmar?";
    setTimeout(() => { if (botao.isConnected) { botao.classList.remove("armado"); botao.textContent = "Cancelar"; } }, 4000);
    return;
  }
  if (estado.emAndamento.has(id)) return;
  estado.emAndamento.add(id);
  const botoes = $$(`#agenda [data-realizar="${id}"], #agenda [data-cancelar="${id}"]`);
  botoes.forEach((b) => (b.disabled = true));
  const nome = estado.agendamentos.find((a) => a.id === Number(id))?.paciente ?? "";
  try {
    if (botao.dataset.realizar) {
      const r = await api("POST", `/agendamentos/${id}/realizar`);
      if (!r.ok) bastidores.registrar(eventoDeErro(r));
      else bastidores.registrar({
        ok: true, status: r.status, titulo: `Atendimento de ${nome} realizado: fatura #${r.dados.id} de ${brl(r.dados.valor_total)}.`,
        regra: `<span class="tipo">PROCEDURE</span> <code>realizar_atendimento</code>, numa transação: convênio ${brl(r.dados.valor_convenio)} + paciente ${brl(r.dados.valor_paciente)}.`,
      });
    } else {
      const r = await api("POST", `/agendamentos/${id}/cancelar`);
      if (!r.ok) bastidores.registrar(eventoDeErro(r));
      else bastidores.registrar({
        ok: true, status: r.status, titulo: `Agendamento de ${nome} cancelado: o horário ficou livre.`,
        regra: "Cancelados ficam fora de <code>sem_conflito_medico</code> (<code>WHERE status &lt;&gt; 'cancelado'</code>).",
      });
    }
  } finally {
    estado.emAndamento.delete(id);
    botoes.forEach((b) => (b.disabled = false)); // se a operação foi recusada, os botões voltam a funcionar
  }
  atualizar();
});

$("#filtro-medico").addEventListener("change", () => render.agenda());

// ---------------------------------------------------------------- carga
// Recria as opções de um <select> sem perder o que a pessoa já escolheu.
function preencher(el, html) {
  const atual = el.value;
  el.innerHTML = html;
  if (atual && [...el.options].some((o) => o.value === atual)) el.value = atual;
  if (el.selectedIndex < 0) el.selectedIndex = 0;   // nunca deixa o select em branco
}

async function carregarCadastros() {
  const [pac, med, conv] = await Promise.all([api("GET", "/pacientes"), api("GET", "/medicos"), api("GET", "/convenios")]);
  if (pac.ok) estado.pacientes = pac.dados;
  if (med.ok) estado.medicos = med.dados;
  let planos = null;
  if (conv.ok) {
    estado.planos = {};
    planos = '<option value="">Particular</option>' + conv.dados.map((c) =>
      `<optgroup label="${esc(c.nome)}">` + c.planos.map((p) => {
        estado.planos[p.id] = `${c.nome} · ${p.nome}`;
        return `<option value="${p.id}">${esc(p.nome)} (${Number(p.cobertura_pct)}%)</option>`;
      }).join("") + "</optgroup>").join("");
  }
  const grupo = (t, l) => l.length ? `<optgroup label="${t}">${l.map((p) => `<option value="${p.id}">${esc(p.nome)}</option>`).join("")}</optgroup>` : "";
  const nomes = [...estado.pacientes].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  const pacientes = grupo("Com plano", nomes.filter((p) => p.plano_id)) + grupo("Particulares", nomes.filter((p) => !p.plano_id));
  const porEsp = {};
  estado.medicos.forEach((m) => (porEsp[m.especialidade] ||= []).push(m));
  const medicos = Object.entries(porEsp).map(([esp, ms]) =>
    `<optgroup label="${esc(esp)}">${ms.map((m) => `<option value="${m.id}">${esc(m.nome)}</option>`).join("")}</optgroup>`).join("");

  // Com uma gaveta aberta, os selects dela não são recriados: o que a pessoa está escolhendo não pode mudar.
  if (!gaveta.atual || !$("#sel-medico").options.length) {
    if (planos) preencher($("#sel-plano"), planos);
    if (pac.ok) preencher($("#sel-paciente"), pacientes);
    if (med.ok) preencher($("#sel-medico"), medicos);
  }
  if (med.ok) preencher($("#filtro-medico"), '<option value="">Todos</option>' + medicos);
  if (pac.ok) render.pacientes();   // não mostra "Nenhum paciente" se a API nem respondeu
}

const caiu = (r) => r.status === 0 || r.status >= 500;

// Mostra no painel quando a API cai e quando volta (um evento por transição, não um a cada 3 s).
function conexao(online) {
  if (online === estado.online) return;
  estado.online = online;
  $("#ao-vivo").classList.toggle("off", !online);
  $("#estado-conexao").textContent = online ? "Respostas do PostgreSQL" : "Sem conexão com a API";
  bastidores.registrar(online
    ? { ok: true, status: 200, titulo: "Conexão com a API restabelecida.", regra: "" }
    : { ok: false, status: 0, titulo: "Sem conexão com a API (localhost:8081).", regra: "Confira se o Docker está rodando." });
}

function erroDeCarga() {
  const msg = vazio("Não foi possível carregar os dados", "Confira se o Docker está rodando e se a API responde em localhost:8081. Tentando de novo a cada 3 segundos.");
  ["#agenda", "#pacientes-tabela", "#faturas", "#auditoria"].forEach((s) => ($(s).innerHTML = msg));
}

async function atualizar() {
  if (estado.carregando) return;   // uma consulta por vez: respostas fora de ordem não mostram dado velho
  estado.carregando = true;
  try {
    const [ag, fat, aud] = await Promise.all([api("GET", "/agendamentos"), api("GET", "/faturas"), api("GET", "/auditoria?limit=30")]);
    conexao(![ag, fat, aud].every(caiu));
    if (!estado.online) {
      if (estado.primeira) erroDeCarga();   // ainda não carregou nada: não finge que o banco está vazio
      return;
    }
    // só redesenha o que mudou: preserva foco e botões durante a requisição
    const mudou = (chave, r) => {
      if (!r.ok) return false;
      const novo = JSON.stringify(r.dados);
      if (novo === estado.ultimo[chave]) return false;
      estado.ultimo[chave] = novo;
      return true;
    };
    if (mudou("ag", ag)) { estado.agendamentos = ag.dados; render.agenda(); }
    if (mudou("fat", fat)) { estado.faturas = fat.dados; render.faturas(); }
    if (mudou("aud", aud)) { estado.auditoria = aud.dados; render.auditoria(); }
    if (ag.ok || fat.ok || aud.ok) estado.primeira = false;
  } finally {
    estado.carregando = false;
  }
}

irPara(location.hash.replace("#/", "") || "agenda");
bastidores.desenhar();
carregarCadastros().then(atualizar);
setInterval(atualizar, 3000);
setInterval(carregarCadastros, 15000);
