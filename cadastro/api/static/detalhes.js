// Detalhes dos "bastidores": mostra, num modal, o que o banco executou numa ação (SQL, Cypher, MongoDB, Redis).
// A API devolve os comandos no cabeçalho X-DB-Log (zlib + base64) quando a requisição manda X-Log: 1.
(() => {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TIPOS = { sql: "SQL", cypher: "Cypher", mongo: "MongoDB", redis: "Redis", lua: "Lua" };
  const PALAVRAS = {
    sql: "SELECT|FROM|WHERE|AND|OR|NOT|JOIN|LEFT|INNER|ON|AS|INSERT|INTO|VALUES|UPDATE|SET|DELETE|RETURNING|ORDER|BY|GROUP|LIMIT|OFFSET|CALL|BEGIN|COMMIT|ROLLBACK|DISTINCT|COUNT|NULL|IN|IS|LIKE|ANY|ALL|CASE|WHEN|THEN|ELSE|END|WITH|UNION|DESC|ASC|FOR|NO|KEY|UPDATE|EXISTS|USING|SAVEPOINT|RELEASE",
    cypher: "MATCH|OPTIONAL|WHERE|AND|OR|NOT|RETURN|DISTINCT|MERGE|CREATE|SET|DELETE|DETACH|WITH|UNION|ORDER|BY|LIMIT|AS|COUNT|IN|IS|NULL|SHOW|CONSTRAINT|IF|EXISTS|FOR|REQUIRE|UNIQUE|ON|DESC|ASC",
    lua: "local|if|then|else|elseif|end|return|for|do|while|and|or|not|nil|true|false|function",
  };

  async function decodificar(valor) {
    if (!valor) return null;
    try {
      const bin = Uint8Array.from(atob(valor), (c) => c.charCodeAt(0));
      const fluxo = new Blob([bin]).stream().pipeThrough(new DecompressionStream("deflate"));
      return JSON.parse(await new Response(fluxo).text());
    } catch { return null; }
  }

  // SQL de uma linha só ganha quebras antes das cláusulas principais; o resto já vem formatado do código
  function formatar(tipo, texto) {
    if (tipo !== "sql" && tipo !== "cypher") return texto;
    const PRINCIPAIS = /^(SELECT|FROM|WHERE|JOIN|LEFT|INNER|INSERT|VALUES|UPDATE|SET|DELETE|RETURNING|ORDER|GROUP|LIMIT|CALL|BEGIN|COMMIT|ROLLBACK|MATCH|OPTIONAL|RETURN|WITH|MERGE|CREATE|UNION|SHOW|UNWIND)\b/i;
    let t = texto;
    if (!t.includes("\n") && t.length > 70) t = t.replace(/\s+(FROM|WHERE|JOIN|LEFT JOIN|GROUP BY|ORDER BY|LIMIT|VALUES|SET|RETURNING|RETURN|MATCH|WITH)\b/g, "\n$1");
    // tira a indentação do código-fonte e recoloca uma só: cláusulas à esquerda, o resto recuado
    return t.split("\n").map((l) => l.trim().replace(/\s{2,}/g, " ")).filter(Boolean).map((l) => (PRINCIPAIS.test(l) ? l : "  " + l)).join("\n");
  }

  function realcar(tipo, bruto) {
    const texto = formatar(tipo, bruto);
    let re;
    if (tipo === "mongo") re = /("(?:[^"\\]|\\.)*")(\s*:)?|\b(-?\d+(?:\.\d+)?)\b|\b(true|false|null)\b/g;
    else if (tipo === "redis") return texto.split("\n").map((l) => { const [c, ...r] = l.split(" "); return `<span class="kw">${esc(c)}</span> ${esc(r.join(" "))}`; }).join("\n");
    else {
      const kw = PALAVRAS[tipo] || PALAVRAS.sql;
      re = new RegExp(`(--[^\\n]*)|('(?:[^']|'')*')|(\\$\\w+)|\\b(\\d+(?:\\.\\d+)?)\\b|\\b(${kw})\\b`, "gi");
    }
    let saida = "", i = 0, m;
    while ((m = re.exec(texto))) {
      saida += esc(texto.slice(i, m.index));
      const t = esc(m[0]);
      if (tipo === "mongo") saida += m[2] ? `<span class="det-chave">${esc(m[1])}</span>${esc(m[2])}` : m[1] ? `<span class="det-str">${t}</span>` : `<span class="det-num">${t}</span>`;
      else saida += m[1] ? `<span class="det-com">${t}</span>` : m[2] ? `<span class="det-str">${t}</span>` : m[3] ? `<span class="det-par">${t}</span>` : m[4] ? `<span class="det-num">${t}</span>` : `<span class="kw">${t}</span>`;
      i = m.index + m[0].length;
    }
    return saida + esc(texto.slice(i));
  }

  function dialogo() {
    let d = document.getElementById("dlg-detalhe");
    if (d) return d;
    d = document.createElement("dialog");
    d.id = "dlg-detalhe"; d.className = "dlg-detalhe"; d.setAttribute("aria-labelledby", "det-titulo");
    d.innerHTML = '<div class="det-topo"><div><h2 id="det-titulo"></h2><div class="det-meta" id="det-meta"></div></div><button type="button" class="botao fantasma icone-so" data-det-fechar aria-label="Fechar"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div><div class="det-corpo" id="det-corpo"></div>';
    document.body.append(d);
    d.addEventListener("click", (e) => {
      if (e.target === d || e.target.closest("[data-det-fechar]")) d.close();
      const c = e.target.closest("[data-det-copiar]");
      if (c) { const t = d.querySelector(`#det-q${c.dataset.detCopiar}`)?.textContent || ""; navigator.clipboard?.writeText(t).then(() => { c.textContent = "Copiado"; setTimeout(() => { c.textContent = "Copiar"; }, 1500); }); }
    });
    return d;
  }

  function abrir(ev) {
    const d = dialogo(), cs = ev.consultas || [];
    $id("det-titulo").textContent = ev.titulo || ev.op || "Operação";
    $id("det-meta").innerHTML = [
      ev.ok === undefined ? "" : `<span class="selo ${ev.ok ? "gravado" : "recusado"}">${ev.ok ? "Gravado" : "Recusado"}</span>`,
      ev.status ? `<span class="det-chip">HTTP ${esc(ev.status)}</span>` : "", ev.op ? `<span class="det-chip mono">${esc(ev.op)}</span>` : "",
      ev.ms != null ? `<span class="det-chip">${Math.round(ev.ms)} ms no total</span>` : "",
    ].join("");
    const regra = ev.regraHtml ? ev.regra : esc(ev.regra || "");
    $id("det-corpo").innerHTML = `
      ${regra || ev.sqlstate ? `<section class="det-sec"><h3>O que o banco fez</h3>${regra ? `<p class="det-regra">${regra}</p>` : ""}${ev.sqlstate ? `<p class="det-sub">SQLSTATE ${esc(ev.sqlstate)}</p>` : ""}</section>` : ""}
      <section class="det-sec"><h3>${cs.length ? `Comandos executados (${cs.length})` : "Comandos executados"}</h3>
        ${cs.length ? cs.map((c, i) => `<article class="det-cmd ${c.erro ? "com-erro" : ""}">
          <header><span class="det-n">${i + 1}</span><span class="det-tipo">${esc(TIPOS[c.tipo] || c.tipo)}</span>
            ${c.ms != null ? `<span class="det-chip">${c.ms} ms</span>` : ""}${c.linhas != null ? `<span class="det-chip">${c.linhas} ${c.linhas === 1 ? "linha" : "linhas"}</span>` : ""}
            <button type="button" class="botao fantasma sm" data-det-copiar="${i}">Copiar</button></header>
          ${c.nota ? `<p class="det-nota">${esc(c.nota)}</p>` : ""}
          <pre class="det-codigo" id="det-q${i}">${realcar(c.tipo, c.texto)}</pre>
          ${c.params ? `<div class="det-params"><span class="det-rot">Valores enviados</span>${Array.isArray(c.params) ? c.params.map((p, k) => `<span class="det-p"><b>$${k + 1}</b> ${esc(p)}</span>`).join("") : Object.entries(c.params).map(([k, v]) => `<span class="det-p"><b>$${esc(k)}</b> ${esc(v)}</span>`).join("")}</div>` : ""}
          ${c.erro ? `<p class="det-erro"><b>O banco recusou:</b> ${esc(c.erro)}</p>` : ""}</article>`).join("") : '<p class="det-vazio">Esta ação não gerou comandos registrados.</p>'}
        ${cs.some((c) => c.tipo === "sql") ? '<p class="det-sub">Constraints e triggers rodam dentro destes comandos, no próprio banco: por isso não aparecem como linhas separadas.</p>' : ""}
      </section>
      ${ev.resposta !== undefined ? `<details class="det-sec"><summary>Resposta da API</summary><pre class="det-codigo">${esc(JSON.stringify(ev.resposta, null, 2))}</pre></details>` : ""}`;
    d.showModal();
  }
  const $id = (i) => document.getElementById(i);

  // linha de rodapé dos cartões de bastidores
  const rodape = (ev) => ev && ev.consultas && ev.consultas.length ? `<p class="det-ver">Ver o que o banco executou · ${ev.consultas.length} ${ev.consultas.length === 1 ? "comando" : "comandos"} ›</p>` : "";

  window.Detalhes = { decodificar, abrir, rodape };
})();
