"""Documentos internos da empresa: termos, regras, procedimentos e formulários.

Todos que entram no sistema consultam; só administradores cadastram, trocam o arquivo e apagam.
O arquivo fica na mesma pasta dos anexos (entra no backup junto).
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import anexos as arquivos_disco
from .anexos import AnexoInvalido, Arquivo
from .modelos import CATEGORIAS_DOCUMENTO, Documento, Usuario
from .servicos import ErroValidacao, _escapar_like

EXTENSOES_DOCUMENTO = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".ods",
                       ".ppt", ".pptx", ".odp", ".png", ".jpg", ".jpeg"}


def listar(s: Session, texto: str = "", categoria: str = "") -> list[Documento]:
    cond = []
    if texto:
        termo = f"%{_escapar_like(texto.strip())}%"
        cond.append(or_(Documento.titulo.ilike(termo, escape="\\"), Documento.descricao.ilike(termo, escape="\\"),
                        Documento.nome.ilike(termo, escape="\\")))
    if categoria:
        cond.append(Documento.categoria == categoria)
    return list(s.scalars(select(Documento).where(*cond).order_by(func.lower(Documento.titulo), Documento.id)))


def contagem_por_categoria(s: Session) -> dict[str, int]:
    return dict(s.execute(select(Documento.categoria, func.count(Documento.id))
                          .group_by(Documento.categoria)).all())


def obter(s: Session, documento_id: int) -> Documento | None:
    return s.get(Documento, documento_id)


def _validar(dados: dict) -> dict:
    titulo = " ".join((dados.get("titulo") or "").split())
    if not titulo or len(titulo) > 150:
        raise ErroValidacao("Informe o título do documento (até 150 caracteres).")
    if dados.get("categoria") not in CATEGORIAS_DOCUMENTO:
        raise ErroValidacao("Escolha a categoria do documento.")
    return {"titulo": titulo, "categoria": dados["categoria"],
            "descricao": (dados.get("descricao") or "").strip()[:2000] or None}


def _conferir_arquivo(arq: Arquivo) -> None:
    if arquivos_disco.extensao(arq.nome) not in EXTENSOES_DOCUMENTO:
        raise AnexoInvalido(f"Tipo de arquivo não aceito para documento: {arq.nome} "
                            "(use PDF, Word, Excel, PowerPoint, texto ou imagem).")


def salvar(s: Session, atual: Documento | None, dados: dict, arq: Arquivo | None, autor: Usuario) -> Documento:
    """Cria (atual=None, arquivo obrigatório) ou atualiza; um arquivo novo substitui o anterior."""
    v = _validar(dados)
    if atual is None and arq is None:
        raise ErroValidacao("Escolha o arquivo do documento.")
    if arq is not None:
        _conferir_arquivo(arq)

    doc = atual or Documento()
    antigo = None
    for campo, valor in v.items():
        setattr(doc, campo, valor)
    if arq is not None:
        antigo = doc.arquivo
        doc.arquivo = arquivos_disco.gravar(arq)
        doc.nome, doc.tipo, doc.tamanho = arq.nome, arq.tipo[:100], len(arq.conteudo)
    doc.autor_id = autor.id
    if atual is None:
        s.add(doc)
    try:
        s.commit()
    except Exception:
        s.rollback()
        if arq is not None:
            arquivos_disco.remover(doc.arquivo)
        raise
    if antigo:
        arquivos_disco.remover(antigo)
    return doc


def apagar(s: Session, doc: Documento) -> None:
    nome = doc.arquivo
    s.delete(doc)
    s.commit()
    arquivos_disco.remover(nome)
