"""Envio de e-mail por SMTP, em segundo plano.

O envio roda numa thread separada para a página não esperar o servidor de e-mail.
Se falhar, o erro vai para o log do serviço (journalctl) e o sistema segue normalmente.
"""

import logging
import os
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from flask import Flask, current_app

from .config import ConfigEmail

log = logging.getLogger("ticket_manager.email")

# Logo embutido nos e-mails (referenciado no HTML como cid:...): programas de e-mail costumam
# bloquear imagens externas, mas mostram as que vêm dentro da mensagem
CID_MARCA = "marca@ticket-manager"
_MARCA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "marca.png")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")


@dataclass
class Mensagem:
    para: str
    assunto: str
    texto: str
    html: str


def iniciar(app: Flask, cfg: ConfigEmail) -> None:
    app.extensions["email"] = cfg
    if cfg.ativo:
        log.info("E-mail ativo: %s:%s (%s)", cfg.host, cfg.porta, cfg.seguranca)
        if cfg.seguranca != "nenhuma" and not cfg.verificar_certificado:
            log.warning("E-mail: verificação do certificado do servidor DESLIGADA (verificar_certificado = false)")


def ativo() -> bool:
    return current_app.extensions["email"].ativo or current_app.config.get("EMAIL_CAPTURA") is not None


def enviar(msg: Mensagem) -> None:
    """Agenda o envio. Nos testes (EMAIL_CAPTURA), só guarda a mensagem numa lista."""
    captura = current_app.config.get("EMAIL_CAPTURA")
    if captura is not None:
        captura.append(msg)
        return
    cfg: ConfigEmail = current_app.extensions["email"]
    if cfg.ativo and msg.para:
        _executor.submit(_enviar_agora, cfg, msg)


def _montar(cfg: ConfigEmail, msg: Mensagem) -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr((cfg.nome, cfg.remetente))
    m["To"] = msg.para
    m["Subject"] = " ".join(msg.assunto.split())  # nunca quebra de linha no cabeçalho
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=cfg.remetente.rsplit("@", 1)[-1])
    m.set_content(msg.texto)
    m.add_alternative(msg.html, subtype="html")
    if f"cid:{CID_MARCA}" in msg.html and os.path.exists(_MARCA):
        with open(_MARCA, "rb") as f:
            m.get_body(("html",)).add_related(f.read(), "image", "png", cid=f"<{CID_MARCA}>",
                                               filename="marca.png", disposition="inline")
    return m


def _enviar_agora(cfg: ConfigEmail, msg: Mensagem) -> None:
    try:
        enviar_sincrono(cfg, msg)
    except Exception:
        log.exception("Falha ao enviar e-mail para %s (%s)", msg.para, msg.assunto)


def _contexto_ssl(cfg: ConfigEmail) -> ssl.SSLContext:
    """Confere o certificado do servidor; aceita o certificado da empresa (ca_arquivo)."""
    contexto = ssl.create_default_context(cafile=cfg.ca_arquivo or None)
    if not cfg.verificar_certificado:
        contexto.check_hostname = False
        contexto.verify_mode = ssl.CERT_NONE
    return contexto


def enviar_sincrono(cfg: ConfigEmail, msg: Mensagem) -> None:
    """Envia na hora e deixa o erro subir (usado pelo comando de teste)."""
    contexto = _contexto_ssl(cfg)
    if cfg.seguranca == "ssl":
        servidor = smtplib.SMTP_SSL(cfg.host, cfg.porta, timeout=20, context=contexto)
    else:
        servidor = smtplib.SMTP(cfg.host, cfg.porta, timeout=20)
    with servidor:
        if cfg.seguranca == "starttls":
            servidor.starttls(context=contexto)
        if cfg.usuario:
            servidor.login(cfg.usuario, cfg.senha)
        servidor.send_message(_montar(cfg, msg))
    log.info("E-mail enviado para %s: %s", msg.para, msg.assunto)
