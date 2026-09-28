// Pequenos comportamentos da interface (o sistema funciona sem JavaScript).

document.addEventListener("DOMContentLoaded", () => {
  // Alterna entre claro e escuro e lembra a escolha neste navegador
  document.querySelectorAll("[data-alternar-tema]").forEach((botao) => {
    botao.addEventListener("click", () => {
      const raiz = document.documentElement;
      const escuroAgora = raiz.dataset.theme
        ? raiz.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      const novo = escuroAgora ? "light" : "dark";
      raiz.dataset.theme = novo;
      try { localStorage.setItem("tema", novo); } catch (e) { /* só vale nesta página */ }
    });
  });

  // Linha da tabela inteira clicável
  document.querySelectorAll("tr[data-href]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest("a, button, input, select")) return;
      window.location = tr.dataset.href;
    });
  });

  // Confirmação antes de ações destrutivas
  document.querySelectorAll("form[data-confirmar]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!window.confirm(form.dataset.confirmar)) e.preventDefault();
    });
  });

  // Mostra os arquivos escolhidos
  document.querySelectorAll("input[data-lista-arquivos]").forEach((input) => {
    const lista = input.closest("form").querySelector(".lista-arquivos");
    input.addEventListener("change", () => {
      lista.replaceChildren(...Array.from(input.files).map((f) => {
        const li = document.createElement("li");
        li.textContent = `📎 ${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB)`;
        return li;
      }));
    });
  });

  // Funcionário: mostra só quem atende o setor escolhido
  document.querySelectorAll("select[data-funcionarios]").forEach((sel) => {
    const setor = sel.form.querySelector("select[data-setor]");
    const aviso = sel.options[0];
    const textoAviso = aviso.textContent;
    const atualizar = () => {
      sel.querySelectorAll("optgroup").forEach((grupo) => {
        const visivel = grupo.dataset.setor === setor.value;
        grupo.hidden = !visivel;
        grupo.disabled = !visivel;
      });
      const escolhida = sel.selectedOptions[0];
      if (escolhida && escolhida.parentElement.disabled) sel.value = "";
      aviso.textContent = setor.value ? "Selecione" : textoAviso;
      // Setor com uma pessoa só: já deixa escolhida
      const visiveis = sel.querySelectorAll("optgroup:not([disabled]) option");
      if (!sel.value && visiveis.length === 1) sel.value = visiveis[0].value;
    };
    setor.addEventListener("change", atualizar);
    atualizar();
  });

  // Formulário com vários campos (ex.: Usuários): destaca as linhas alteradas,
  // conta as alterações e avisa antes de sair da página sem salvar
  document.querySelectorAll("form[data-avisar-alteracoes]").forEach((form) => {
    const campos = Array.from(form.elements).filter((c) => c.type !== "hidden" && c.name);
    const valor = (c) => (c.type === "checkbox" ? c.checked : c.value);
    const original = new Map(campos.map((c) => [c, valor(c)]));
    const contador = document.querySelector("[data-contador-alteracoes]");
    const textoInicial = contador ? contador.textContent : "";
    let enviando = false;
    const alterados = () => campos.filter((c) => valor(c) !== original.get(c));
    const atualizar = () => {
      const lista = alterados();
      campos.forEach((c) => c.closest("tr")?.classList.remove("linha-alterada"));
      lista.forEach((c) => c.closest("tr")?.classList.add("linha-alterada"));
      const linhas = new Set(lista.map((c) => c.closest("tr"))).size;
      if (contador) {
        contador.textContent = linhas
          ? `${linhas} usuário${linhas > 1 ? "s" : ""} com alterações não salvas.`
          : textoInicial;
      }
    };
    campos.forEach((c) => c.addEventListener("change", atualizar));
    form.addEventListener("submit", () => { enviando = true; });
    window.addEventListener("beforeunload", (e) => {
      if (!enviando && alterados().length) { e.preventDefault(); e.returnValue = ""; }
    });
  });

  // Envia o formulário ao mudar o select (ex.: período do painel)
  document.querySelectorAll("select[data-enviar-ao-mudar]").forEach((sel) => {
    sel.addEventListener("change", () => sel.form.submit());
  });

  // Evita envio duplo
  document.querySelectorAll("form[method='post']").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (e.defaultPrevented) return;
      setTimeout(() => form.querySelectorAll("button[type='submit'], button:not([type])")
        .forEach((b) => { b.disabled = true; }), 0);
    });
  });
});
