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

  // Cor do sistema: cor principal + intensidade (1–5); a escolha fica neste navegador
  document.querySelectorAll("[data-seletor-cor]").forEach((caixa) => {
    const raiz = document.documentElement;
    const abrir = caixa.querySelector("[data-abrir-paleta]");
    const paleta = caixa.querySelector(".paleta");
    const amostras = Array.from(paleta.querySelectorAll("[data-cor]"));
    const faixa = paleta.querySelector("[data-intensidade-cor]");
    const nomeFaixa = paleta.querySelector("[data-nome-intensidade]");
    const nomes = (faixa.dataset.nomes || "").split("|");
    const salvar = (chave, valor) => {
      try { localStorage.setItem(chave, valor); } catch (e) { /* só vale nesta página */ }
    };
    const marcar = () => {
      const atual = raiz.dataset.cor || "padrao";
      amostras.forEach((a) => a.setAttribute("aria-checked", String(a.dataset.cor === atual)));
      faixa.value = raiz.dataset.intensidade || faixa.value;
      faixa.disabled = atual === "padrao";
      nomeFaixa.textContent = faixa.disabled ? "—" : (nomes[faixa.value - 1] || faixa.value);
    };
    const fechar = () => { paleta.hidden = true; abrir.setAttribute("aria-expanded", "false"); };
    abrir.addEventListener("click", (e) => {
      e.stopPropagation();
      paleta.hidden = !paleta.hidden;
      abrir.setAttribute("aria-expanded", String(!paleta.hidden));
      marcar();
    });
    amostras.forEach((a) => a.addEventListener("click", () => {
      if (a.dataset.cor === "padrao") {
        delete raiz.dataset.cor;
        delete raiz.dataset.intensidade;
      } else {
        raiz.dataset.cor = a.dataset.cor;
        raiz.dataset.intensidade = faixa.value;
        salvar("intensidade", faixa.value);
      }
      salvar("cor", a.dataset.cor);
      marcar();
    }));
    // Muda ao arrastar (prévia ao vivo) e guarda o valor
    faixa.addEventListener("input", () => {
      if (!raiz.dataset.cor) return;
      raiz.dataset.intensidade = faixa.value;
      salvar("intensidade", faixa.value);
      marcar();
    });
    document.addEventListener("click", (e) => { if (!caixa.contains(e.target)) fechar(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") fechar(); });
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

  // Inventário: campos de configuração só para computadores; usuário preenche o setor
  document.querySelectorAll("select[data-tipo-equipamento]").forEach((tipo) => {
    const computadores = (tipo.dataset.computador || "").split("|");
    const bloco = tipo.form.querySelector("[data-campos-computador]");
    const atualizar = () => {
      // Sem tipo escolhido ou com dados já preenchidos, mostra (não esconde informação existente)
      const preenchido = bloco && Array.from(bloco.querySelectorAll("input")).some((i) => i.value);
      if (bloco) bloco.hidden = !(computadores.includes(tipo.value) || !tipo.value || preenchido);
    };
    tipo.addEventListener("change", atualizar);
    atualizar();
  });
  document.querySelectorAll("select[data-usuario-equipamento]").forEach((sel) => {
    const setor = sel.form.querySelector("select[data-setor-equipamento]");
    sel.addEventListener("change", () => {
      const escolhido = sel.selectedOptions[0];
      if (setor && escolhido && escolhido.dataset.setor) setor.value = escolhido.dataset.setor;
    });
  });

  // Máscaras: MAC ganha ":" a cada 2 dígitos; licença do Windows, "-" a cada 5 caracteres
  const MASCARAS = {
    mac: { permitido: /[^0-9a-f]/gi, tamanho: 12, grupo: 2, separador: ":" },
    licenca: { permitido: /[^0-9a-z]/gi, tamanho: 25, grupo: 5, separador: "-" },
  };
  document.querySelectorAll("input[data-mascara]").forEach((input) => {
    const m = MASCARAS[input.dataset.mascara];
    if (!m) return;
    const formatar = () => {
      const limpo = input.value.replace(m.permitido, "").toUpperCase().slice(0, m.tamanho);
      const partes = limpo.match(new RegExp(`.{1,${m.grupo}}`, "g")) || [];
      const novo = partes.join(m.separador);
      if (novo !== input.value) input.value = novo;
    };
    input.addEventListener("input", formatar);
    formatar();
  });

  // Checklist da preventiva: marca OK nos itens ainda sem resposta
  document.querySelectorAll("[data-marcar-ok]").forEach((botao) => {
    botao.addEventListener("click", () => {
      const form = botao.closest("form");
      const grupos = new Set(Array.from(form.querySelectorAll(".checklist input[type=radio]")).map((r) => r.name));
      grupos.forEach((nome) => {
        if (form.querySelector(`input[name="${nome}"]:checked`)) return;
        const ok = form.querySelector(`input[name="${nome}"][value="OK"]`);
        if (ok) { ok.checked = true; ok.dispatchEvent(new Event("change", { bubbles: true })); }
      });
    });
  });

  // Documentos: o vencimento só aparece para a categoria Contratos
  document.querySelectorAll("select[data-categoria-documento]").forEach((sel) => {
    const bloco = sel.form.querySelector("[data-so-contratos]");
    const atualizar = () => { if (bloco) bloco.hidden = sel.value !== "Contratos"; };
    sel.addEventListener("change", atualizar);
    atualizar();
  });

  // Diagramas: zoom (botões e Ctrl + rolagem) e arrastar para mover
  document.querySelectorAll("[data-visualizador]").forEach((vis) => {
    const area = vis.querySelector("[data-visualizador-area]");
    const img = vis.querySelector("[data-visualizador-imagem]");
    const rotulo = vis.querySelector("[data-zoom-valor]");
    let zoom = 1;
    const base = () => img.naturalWidth || 1000;
    const aplicar = (novo, foco) => {
      const antes = zoom;
      zoom = Math.min(8, Math.max(0.05, novo));
      // mantém o ponto sob o mouse (ou o centro) no mesmo lugar
      const fx = foco ? foco.x : area.clientWidth / 2;
      const fy = foco ? foco.y : area.clientHeight / 2;
      const px = (area.scrollLeft + fx) / antes, py = (area.scrollTop + fy) / antes;
      img.style.width = `${Math.round(base() * zoom)}px`;
      area.scrollLeft = px * zoom - fx;
      area.scrollTop = py * zoom - fy;
      rotulo.textContent = `${Math.round(zoom * 100)}%`;
    };
    const ajustar = () => {
      const w = img.naturalWidth || 1, h = img.naturalHeight || 1;
      aplicar(Math.min(area.clientWidth / w, area.clientHeight / h) * 0.98);
      area.scrollLeft = 0; area.scrollTop = 0;
    };
    if (img.complete) ajustar(); else img.addEventListener("load", ajustar);
    vis.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
      const acao = b.dataset.zoom;
      if (acao === "mais") aplicar(zoom * 1.25);
      else if (acao === "menos") aplicar(zoom / 1.25);
      else if (acao === "real") aplicar(1);
      else ajustar();
    }));
    area.addEventListener("wheel", (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const r = area.getBoundingClientRect();
      aplicar(zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), { x: e.clientX - r.left, y: e.clientY - r.top });
    }, { passive: false });
    let arrasto = null;
    area.addEventListener("pointerdown", (e) => {
      arrasto = { x: e.clientX, y: e.clientY, l: area.scrollLeft, t: area.scrollTop };
      area.classList.add("arrastando");
      area.setPointerCapture(e.pointerId);
    });
    area.addEventListener("pointermove", (e) => {
      if (!arrasto) return;
      area.scrollLeft = arrasto.l - (e.clientX - arrasto.x);
      area.scrollTop = arrasto.t - (e.clientY - arrasto.y);
    });
    const soltar = () => { arrasto = null; area.classList.remove("arrastando"); };
    area.addEventListener("pointerup", soltar);
    area.addEventListener("pointercancel", soltar);
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
