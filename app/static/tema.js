// Aplica o tema salvo (claro/escuro) antes de desenhar a página, para não piscar.
// Carregado no <head> sem defer; o botão de alternar fica em app.js.
(function () {
  try {
    var tema = localStorage.getItem("tema");
    if (tema === "dark" || tema === "light") document.documentElement.dataset.theme = tema;
    var cor = localStorage.getItem("cor");
    if (cor && cor !== "padrao" && /^[a-z]+$/.test(cor)) {
      var n = localStorage.getItem("intensidade");
      document.documentElement.dataset.cor = cor;
      document.documentElement.dataset.intensidade = /^[1-5]$/.test(n || "") ? n : "3";
    }
  } catch (e) { /* navegador sem localStorage: segue o tema do sistema */ }
})();
