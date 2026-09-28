"""Anexos: validação do upload e gravação em disco."""

import os
import secrets
from dataclasses import dataclass

from flask import current_app
from werkzeug.datastructures import FileStorage

EXTENSOES_PERMITIDAS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".pdf", ".txt", ".log", ".csv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
    ".zip", ".7z", ".rar", ".xml", ".json", ".eml", ".msg",
}
MAX_ARQUIVOS = 5

# Tipos que o navegador pode exibir direto (o resto sempre é baixado)
TIPOS_EXIBIVEIS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
}


class AnexoInvalido(ValueError):
    pass


@dataclass
class Arquivo:
    nome: str
    tipo: str
    conteudo: bytes


def nome_seguro(nome: str) -> str:
    nome = os.path.basename((nome or "").replace("\\", "/")).strip()
    nome = "".join(c for c in nome if c.isprintable() and c not in '<>:"/\\|?*')
    return nome[:200] or "arquivo"


def extensao(nome: str) -> str:
    return os.path.splitext(nome)[1].lower()


def ler_anexos(arquivos: list[FileStorage]) -> list[Arquivo]:
    """Valida e lê os arquivos do formulário. Lança AnexoInvalido com a mensagem para o usuário."""
    arquivos = [a for a in arquivos if a and a.filename]
    if len(arquivos) > MAX_ARQUIVOS:
        raise AnexoInvalido(f"Envie no máximo {MAX_ARQUIVOS} arquivos por vez.")

    limite = current_app.config["ANEXO_MAX_BYTES"]
    resultado = []
    for a in arquivos:
        nome = nome_seguro(a.filename)
        if extensao(nome) not in EXTENSOES_PERMITIDAS:
            raise AnexoInvalido(f"Tipo de arquivo não permitido: {nome}")
        conteudo = a.read(limite + 1)
        if len(conteudo) > limite:
            raise AnexoInvalido(f"{nome} passa do limite de {limite // (1024 * 1024)} MB.")
        if not conteudo:
            raise AnexoInvalido(f"{nome} está vazio.")
        resultado.append(Arquivo(nome=nome, tipo=a.mimetype or "application/octet-stream",
                                 conteudo=conteudo))
    return resultado


# ─── disco ──────────────────────────────────────────────────────────────────

def _pasta() -> str:
    return current_app.config["ANEXOS_PASTA"]


def caminho(arquivo: str) -> str:
    # arquivo é sempre gerado por gravar(); basename impede sair da pasta
    return os.path.join(_pasta(), os.path.basename(arquivo))


def gravar(arq: Arquivo) -> str:
    """Grava o conteúdo com um nome aleatório e devolve esse nome."""
    os.makedirs(_pasta(), exist_ok=True)
    nome_disco = secrets.token_hex(16) + extensao(arq.nome)
    with open(caminho(nome_disco), "xb") as f:
        f.write(arq.conteudo)
    return nome_disco


def remover(arquivo: str) -> None:
    try:
        os.remove(caminho(arquivo))
    except FileNotFoundError:
        pass
