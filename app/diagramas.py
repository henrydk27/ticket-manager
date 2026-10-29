"""Diagramas da infraestrutura (mapa da rede, câmeras...): imagem para ver no sistema e o
arquivo editável do draw.io para baixar e atualizar.

Administradores e quem atende a T.I veem; só administradores cadastram, trocam e apagam.
Os arquivos ficam na pasta dos anexos (entram no backup) — nunca no repositório, porque
mostram IPs e a estrutura da rede interna.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import anexos as arquivos_disco
from .anexos import AnexoInvalido, Arquivo
from .modelos import Diagrama, Usuario
from .servicos import ErroValidacao

# Imagem: o que o navegador mostra. Dica: no draw.io, "Arquivo → Exportar como → SVG" com
# "Incluir uma cópia do meu diagrama" marcado gera um .drawio.svg que é imagem E editável.
EXTENSOES_IMAGEM = {".svg", ".png", ".jpg", ".jpeg"}
EXTENSOES_EDITAVEL = {".drawio", ".xml", ".vsdx"}
TIPOS_IMAGEM = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def listar(s: Session) -> list[Diagrama]:
    return list(s.scalars(select(Diagrama).order_by(Diagrama.ordem, func.lower(Diagrama.titulo), Diagrama.id)))


def obter(s: Session, diagrama_id: int) -> Diagrama | None:
    return s.get(Diagrama, diagrama_id)


def editavel_embutido(nome: str) -> bool:
    """.drawio.svg / .drawio.png já trazem o diagrama editável dentro da imagem."""
    return nome.lower().endswith((".drawio.svg", ".drawio.png"))


def _validar(dados: dict) -> dict:
    titulo = " ".join((dados.get("titulo") or "").split())
    if not titulo or len(titulo) > 150:
        raise ErroValidacao("Informe o título do diagrama (até 150 caracteres).")
    try:
        ordem = int(dados.get("ordem") or 0)
    except ValueError:
        raise ErroValidacao("Ordem: use um número (os menores aparecem primeiro).") from None
    return {"titulo": titulo, "ordem": max(0, min(ordem, 999)),
            "descricao": (dados.get("descricao") or "").strip()[:2000] or None}


def salvar(s: Session, atual: Diagrama | None, dados: dict, imagem: Arquivo | None, editavel: Arquivo | None,
           autor: Usuario, remover_editavel: bool = False) -> Diagrama:
    """Cria (imagem obrigatória) ou atualiza; arquivos novos substituem os anteriores."""
    v = _validar(dados)
    if atual is None and imagem is None:
        raise ErroValidacao("Escolha a imagem do diagrama (SVG ou PNG exportado do draw.io).")
    if imagem is not None and arquivos_disco.extensao(imagem.nome) not in EXTENSOES_IMAGEM:
        raise AnexoInvalido(f"A imagem precisa ser SVG, PNG ou JPG: {imagem.nome}")
    if editavel is not None and arquivos_disco.extensao(editavel.nome) not in EXTENSOES_EDITAVEL:
        raise AnexoInvalido(f"O arquivo editável precisa ser .drawio (ou .xml/.vsdx): {editavel.nome}")

    d = atual or Diagrama()
    for campo, valor in v.items():
        setattr(d, campo, valor)
    novos, antigos = [], []
    if imagem is not None:
        antigos.append(d.arquivo)
        d.arquivo = arquivos_disco.gravar(imagem)
        novos.append(d.arquivo)
        d.nome, d.tamanho = imagem.nome, len(imagem.conteudo)
    if editavel is not None:
        antigos.append(d.editavel_arquivo)
        d.editavel_arquivo = arquivos_disco.gravar(editavel)
        novos.append(d.editavel_arquivo)
        d.editavel_nome, d.editavel_tamanho = editavel.nome, len(editavel.conteudo)
    elif remover_editavel and d.editavel_arquivo:
        antigos.append(d.editavel_arquivo)
        d.editavel_arquivo = d.editavel_nome = d.editavel_tamanho = None
    d.autor_id = autor.id
    if atual is None:
        s.add(d)
    try:
        s.commit()
    except Exception:
        s.rollback()
        for nome in novos:
            arquivos_disco.remover(nome)
        raise
    for nome in antigos:
        if nome:
            arquivos_disco.remover(nome)
    return d


def apagar(s: Session, d: Diagrama) -> None:
    nomes = [d.arquivo, d.editavel_arquivo]
    s.delete(d)
    s.commit()
    for nome in nomes:
        if nome:
            arquivos_disco.remover(nome)
