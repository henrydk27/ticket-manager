"""Ticket Manager Web — criação da aplicação Flask."""

from datetime import timedelta

from flask import Flask, g, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from . import banco, correio, formatos, seguranca
from .config import Config, carregar_config
from .modelos import AVALIACOES, PAPEIS, PRIORIDADES, SETORES, STATUS


def create_app(cfg: Config | None = None) -> Flask:
    cfg = cfg or carregar_config()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=cfg.secret_key,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg.sessao_horas),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cfg.cookie_seguro,
        ANEXOS_PASTA=cfg.anexos_pasta,
        ANEXO_MAX_BYTES=cfg.anexo_max_mb * 1024 * 1024,
        # Folga para até 5 anexos + campos do formulário
        MAX_CONTENT_LENGTH=cfg.anexo_max_mb * 1024 * 1024 * 5 + 1024 * 1024,
        CADASTRO_ABERTO=cfg.cadastro_aberto,
    )
    if cfg.atras_de_proxy:
        # Atrás do Nginx: usa o IP real do cliente (limite de tentativas de login) e o esquema https.
        # Só ative com proxy na frente; sem ele, o cabeçalho X-Forwarded-For poderia ser forjado.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    banco.iniciar(app, cfg.banco_url)
    correio.iniciar(app, cfg.email)
    formatos.registrar(app)
    app.jinja_env.globals.update(csrf_token=seguranca.csrf_token, STATUS=STATUS, SETORES=SETORES,
                                 PRIORIDADES=PRIORIDADES, AVALIACOES=AVALIACOES, PAPEIS=PAPEIS)

    @app.before_request
    def _antes():
        seguranca.verificar_csrf()
        seguranca.carregar_usuario()
        return seguranca.exigir_troca_de_senha() or seguranca.exigir_email()

    @app.after_request
    def _cabecalhos(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        return resp

    def _erro(codigo, titulo, mensagem):
        return render_template("erro.html", codigo=codigo, titulo=titulo, mensagem=mensagem), codigo

    app.register_error_handler(400, lambda e: _erro(400, "Requisição inválida",
                                                    "Recarregue a página e tente de novo."))
    app.register_error_handler(403, lambda e: _erro(403, "Acesso negado",
                                                    "Você não tem permissão para acessar esta página."))
    app.register_error_handler(404, lambda e: _erro(404, "Não encontrado",
                                                    "A página ou o chamado não existe."))
    app.register_error_handler(413, lambda e: _erro(413, "Arquivo grande demais",
                                                    f"O limite é de {cfg.anexo_max_mb} MB por arquivo."))
    app.register_error_handler(500, lambda e: _erro(500, "Erro interno",
                                                    "Algo deu errado. Se continuar, avise o suporte."))

    from .rotas import admin, auth, chamados, conta
    for modulo in (auth, conta, chamados, admin):
        app.register_blueprint(modulo.bp)

    @app.context_processor
    def _contexto():
        return {"usuario": g.get("usuario")}

    return app
