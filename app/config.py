"""Leitura do config.ini (fica fora do Git).

O caminho pode ser trocado pela variável de ambiente TICKET_MANAGER_CONFIG
(ex.: /etc/ticket-manager/config.ini no servidor).
"""

import configparser
import os
from dataclasses import dataclass, field

PASTA_WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class ConfigEmail:
    """Servidor SMTP para os avisos. Sem host, o sistema funciona sem enviar e-mails."""
    host: str = ""
    porta: int = 587
    seguranca: str = "starttls"   # starttls, ssl ou nenhuma
    usuario: str = ""
    senha: str = ""
    remetente: str = ""           # ex.: chamados@empresa.com.br
    nome: str = "Ticket Manager"  # nome que aparece como remetente
    url_site: str = ""            # endereço do sistema nos links (ex.: http://chamados.empresa.local)

    @property
    def ativo(self) -> bool:
        return bool(self.host and self.remetente)


@dataclass
class Config:
    banco_url: str
    secret_key: str
    sessao_horas: int = 10
    anexos_pasta: str = os.path.join(PASTA_WEB, "anexos")
    anexo_max_mb: int = 10
    cadastro_aberto: bool = True
    cookie_seguro: bool = False  # True quando o site estiver em HTTPS
    atras_de_proxy: bool = False  # True quando o Nginx estiver na frente
    email: ConfigEmail = field(default_factory=ConfigEmail)


def caminho_config() -> str:
    return os.environ.get("TICKET_MANAGER_CONFIG") or os.path.join(PASTA_WEB, "config.ini")


def carregar_config() -> Config:
    caminho = caminho_config()
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {caminho}\n"
            "Copie config.example.ini para config.ini e preencha os dados."
        )

    ini = configparser.ConfigParser(interpolation=None)
    ini.read(caminho, encoding="utf-8")
    banco, srv = ini["banco"], ini["servidor"]

    secret = srv.get("secret_key", "").strip()
    if len(secret) < 32:
        raise ValueError("Defina em [servidor] uma secret_key com pelo menos 32 caracteres.")

    email = ConfigEmail()
    if ini.has_section("email"):
        e = ini["email"]
        seguranca = e.get("seguranca", "starttls").strip().lower()
        if seguranca not in ("starttls", "ssl", "nenhuma"):
            raise ValueError("Em [email], seguranca deve ser starttls, ssl ou nenhuma.")
        email = ConfigEmail(
            host=e.get("host", "").strip(),
            porta=e.getint("porta", fallback=587),
            seguranca=seguranca,
            usuario=e.get("usuario", "").strip(),
            senha=e.get("senha", ""),
            remetente=e.get("remetente", "").strip(),
            nome=e.get("nome", "Ticket Manager").strip() or "Ticket Manager",
            url_site=e.get("url_site", "").strip().rstrip("/"),
        )

    pasta = srv.get("anexos_pasta", "").strip() or Config.anexos_pasta
    return Config(
        banco_url=banco.get("url", "").strip(),
        secret_key=secret,
        sessao_horas=srv.getint("sessao_horas", fallback=10),
        anexos_pasta=os.path.abspath(pasta),
        anexo_max_mb=srv.getint("anexo_max_mb", fallback=10),
        cadastro_aberto=srv.getboolean("cadastro_aberto", fallback=True),
        cookie_seguro=srv.getboolean("cookie_seguro", fallback=False),
        atras_de_proxy=srv.getboolean("atras_de_proxy", fallback=False),
        email=email,
    )
