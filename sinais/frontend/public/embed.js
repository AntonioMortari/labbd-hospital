// Dentro do shell o módulo abre com ?embed=1 e esconde o que o shell já mostra (marca, rodapés).
if (new URLSearchParams(location.search).get("embed") === "1") document.documentElement.classList.add("embed");
