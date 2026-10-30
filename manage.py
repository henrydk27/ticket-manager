"""Comandos de administração.

    python manage.py migrar                 cria/atualiza as tabelas do banco
    python manage.py criar-admin LOGIN      cria um administrador (pede nome, setor e senha)
    python manage.py tornar-admin LOGIN     promove uma conta existente a administrador
    python manage.py testar-email DESTINO   envia um e-mail de teste (confere a seção [email])
    python manage.py avisar-semanal         resumo semanal ao CPD: preventivas, contratos e tarefas (agendar no cron)
    python manage.py avisos-diarios         lembretes de avaliação e de tarefas da T.I (agendar no cron)
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
    email = input("E-mail: ").strip()
    print("Setores:", ", ".join(SETORES))
    setor = input("Setor: ").strip()
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Confirme a senha: "):
        sys.exit("As senhas não conferem.")
    with _sessao() as s:
        try:
            u = servicos.criar_conta(s, nome, login, email, setor, senha)
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


def testar_email(destino: str) -> None:
    from app.config import carregar_config
    from app.correio import Mensagem, enviar_sincrono

    cfg = carregar_config().email
    if not cfg.ativo:
        sys.exit("E-mail desligado: preencha host e remetente na seção [email] do config.ini.")
    print(f"Enviando por {cfg.host}:{cfg.porta} ({cfg.seguranca}) como {cfg.remetente}...")
    texto = "Se você recebeu esta mensagem, os avisos por e-mail do Ticket Manager estão funcionando."
    try:
        enviar_sincrono(cfg, Mensagem(para=destino, assunto="Ticket Manager: e-mail de teste",
                                      texto=texto, html=f"<p>{texto}</p>"))
    except Exception as e:  # mostra o erro do servidor SMTP de forma legível
        sys.exit(f"Falhou: {type(e).__name__}: {e}")
    print("Enviado. Confira a caixa de entrada (e o spam) de", destino)


def avisar_semanal() -> None:
    """Resumo semanal ao CPD: preventivas pendentes, contratos vencendo/vencidos e tarefas atrasadas."""
    from app import create_app, documentos, notificacoes, preventivas, tarefas
    from app.config import carregar_config
    from app.correio import enviar_sincrono

    cfg = carregar_config()
    if not cfg.email.ativo:
        sys.exit("E-mail desligado: preencha host e remetente na seção [email] do config.ini.")
    app = create_app(cfg)
    with app.test_request_context(base_url=cfg.email.url_site or "http://localhost"):
        s = app.extensions["sessoes"]()
        try:
            pendentes = preventivas.pendentes(s)
            contratos = documentos.contratos_a_vencer(s)
            atrasadas = tarefas.atrasadas(s)
            msg = notificacoes.mensagem_semanal(pendentes, contratos, atrasadas)
            if msg is None:
                print("Nenhuma preventiva pendente, contrato vencendo nem tarefa atrasada: nada enviado.")
                return
            enviar_sincrono(cfg.email, msg)
            print(f"Enviado para {msg.para}: {len(pendentes)} preventiva(s), {len(contratos)} contrato(s) "
                  f"e {len(atrasadas)} tarefa(s) atrasada(s).")
        finally:
            s.close()


def avisos_diarios() -> None:
    """Avisos do dia por e-mail: chamados encerrados esperando avaliação (para quem abriu) e
    tarefas da T.I atrasadas, de hoje ou no prazo de aviso (para o responsável ou toda a T.I)."""
    from app import create_app, notificacoes, servicos, tarefas
    from app.config import carregar_config
    from app.correio import enviar_sincrono

    cfg = carregar_config()
    if not cfg.email.ativo:
        sys.exit("E-mail desligado: preencha host e remetente na seção [email] do config.ini.")
    app = create_app(cfg)
    with app.test_request_context(base_url=cfg.email.url_site or "http://localhost"):
        s = app.extensions["sessoes"]()
        falhas = 0

        def enviar(u, msg) -> bool:
            nonlocal falhas
            if msg is None:
                return False
            try:
                enviar_sincrono(cfg.email, msg)
            except Exception as e:          # um e-mail com problema não impede os outros
                falhas += 1
                print(f"Falhou para {u.login}: {type(e).__name__}: {e}")
                return False
            return True

        try:
            avaliacoes = 0
            for u, chamados in servicos.lembretes_de_avaliacao(s).items():
                if enviar(u, notificacoes.mensagem_lembrete_avaliacao(u, chamados)):
                    servicos.registrar_lembretes(s, chamados)
                    avaliacoes += 1
            avisos_tarefas = sum(enviar(u, notificacoes.mensagem_tarefas(u, itens))
                                 for u, itens in tarefas.avisos_do_dia(s).items())
            print(f"Lembretes de avaliação: {avaliacoes} · avisos de tarefas: {avisos_tarefas}"
                  + (f" · falhas: {falhas}" if falhas else ""))
        finally:
            s.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Administração do Ticket Manager")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("migrar", help="cria/atualiza as tabelas")
    sub.add_parser("criar-admin", help="cria um administrador").add_argument("login")
    sub.add_parser("tornar-admin", help="promove uma conta a administrador").add_argument("login")
    sub.add_parser("testar-email", help="envia um e-mail de teste").add_argument("destino")
    sub.add_parser("avisar-semanal", help="resumo semanal ao CPD: preventivas, contratos e tarefas")
    sub.add_parser("avisar-preventivas", help="mesmo que avisar-semanal (nome antigo)")
    sub.add_parser("avisos-diarios", help="lembretes de avaliação e de tarefas da T.I")
    sub.add_parser("lembrar-avaliacoes", help="mesmo que avisos-diarios (nome antigo)")
    a = p.parse_args()
    {"migrar": lambda: migrar(),
     "criar-admin": lambda: criar_admin(a.login),
     "tornar-admin": lambda: tornar_admin(a.login),
     "testar-email": lambda: testar_email(a.destino),
     "avisar-semanal": lambda: avisar_semanal(),
     "avisar-preventivas": lambda: avisar_semanal(),
     "avisos-diarios": lambda: avisos_diarios(),
     "lembrar-avaliacoes": lambda: avisos_diarios()}[a.comando]()


if __name__ == "__main__":
    main()
