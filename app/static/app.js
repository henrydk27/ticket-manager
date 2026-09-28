// Pequenos comportamentos da interface (o sistema funciona sem JavaScript).

document.addEventListener("DOMContentLoaded", () => {
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
