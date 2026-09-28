"""Envio de e-mail por SMTP, em segundo plano.

O envio roda numa thread separada para a página não esperar o servidor de e-mail.
Se falhar, o erro vai para o log do serviço (journalctl) e o sistema segue normalmente.
"""

import logging
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from flask import Flask, current_app

from .config import ConfigEmail

log = logging.getLogger("ticket_manager.email")
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
    return m


def _enviar_agora(cfg: ConfigEmail, msg: Mensagem) -> None:
    try:
        enviar_sincrono(cfg, msg)
    except Exception:
        log.exception("Falha ao enviar e-mail para %s (%s)", msg.para, msg.assunto)


def enviar_sincrono(cfg: ConfigEmail, msg: Mensagem) -> None:
    """Envia na hora e deixa o erro subir (usado pelo comando de teste)."""
    contexto = ssl.create_default_context()
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
