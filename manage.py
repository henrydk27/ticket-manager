"""Comandos de administração.

    python manage.py migrar                 cria/atualiza as tabelas do banco
    python manage.py criar-admin LOGIN      cria um administrador (pede nome, setor e senha)
    python manage.py tornar-admin LOGIN     promove uma conta existente a administrador
"""

import argparse
import getpass
import os
import sys

from alembic import command
from alembic.config import Config as AlembicConfig

PASTA = os.path.dirname(os.path.abspath(__file__))


def migrar() -> None:
    command.upgrade(AlembicConfig(os.path.join(PASTA, "alembic.ini")), "head")
    print("Banco atualizado.")


def _sessao():
    from sqlalchemy.orm import Session

    from app.banco import criar_engine
    from app.config import carregar_config
    return Session(criar_engine(carregar_config().banco_url))


def criar_admin(login: str) -> None:
    from app import servicos
    from app.modelos import PAPEL_ADMIN, SETORES

    nome = input("Nome completo: ").strip()
    print("Setores:", ", ".join(SETORES))
    setor = input("Setor: ").strip()
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Confirme a senha: "):
        sys.exit("As senhas não conferem.")
    with _sessao() as s:
        try:
            u = servicos.criar_conta(s, nome, login, "", setor, senha)
        except servicos.ErroValidacao as e:
            sys.exit(str(e))
        u.papel = PAPEL_ADMIN
        s.commit()
        print(f"Administrador {u.login} criado.")


def tornar_admin(login: str) -> None:
    from sqlalchemy import select

    from app.modelos import PAPEL_ADMIN, Usuario
    with _sessao() as s:
        u = s.scalar(select(Usuario).where(Usuario.login == login.strip().lower()))
        if u is None:
            sys.exit(f"Usuário {login} não encontrado.")
        u.papel, u.ativo = PAPEL_ADMIN, True
        s.commit()
        print(f"{u.login} agora é administrador.")


def main() -> None:
    p = argparse.ArgumentParser(description="Administração do Ticket Manager")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("migrar", help="cria/atualiza as tabelas")
    sub.add_parser("criar-admin", help="cria um administrador").add_argument("login")
    sub.add_parser("tornar-admin", help="promove uma conta a administrador").add_argument("login")
    a = p.parse_args()
    {"migrar": lambda: migrar(),
     "criar-admin": lambda: criar_admin(a.login),
     "tornar-admin": lambda: tornar_admin(a.login)}[a.comando]()


if __name__ == "__main__":
    main()
