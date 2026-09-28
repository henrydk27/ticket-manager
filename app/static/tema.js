// Aplica o tema salvo (claro/escuro) antes de desenhar a página, para não piscar.
// Carregado no <head> sem defer; o botão de alternar fica em app.js.
(function () {
  try {
    var tema = localStorage.getItem("tema");
    if (tema === "dark" || tema === "light") document.documentElement.dataset.theme = tema;
  } catch (e) { /* navegador sem localStorage: segue o tema do sistema */ }
})();
