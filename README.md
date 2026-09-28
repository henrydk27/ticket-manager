# Ticket Manager Web

Sistema de chamados acessado pelo navegador, para **qualquer setor** da empresa: T.I,
Manutenção, RH, Compras... Feito em Python (Flask) com banco **PostgreSQL**, para rodar num
servidor **Ubuntu**. Refeito do zero a partir das funções da versão Lazarus.

## Como funciona

- Cada setor que atende pedidos é uma **fila**, cadastrada pelo administrador, com seus
  **atendentes** e **tipos de pedido** (ex.: T.I → Impressora, Acesso e senha).
- Quem abre o chamado escolhe **para qual setor** é o pedido e o tipo.
- **Cada atendente vê só as filas dele.** Pode assumir, atribuir a um colega da fila, mudar o
  status e **transferir** o chamado para outra fila.

| Todos | Atendentes (das suas filas) | Administradores |
|---|---|---|
| Criar a própria conta | Ver e atender os chamados da fila | Ver e atender **todas** as filas |
| Abrir chamado para qualquer setor, com anexos | Assumir / atribuir a outro atendente da fila | Criar filas, escolher atendentes e tipos de pedido |
| Comentar e anexar arquivos | Mudar status (Aberto, Em andamento, Aguardando usuário, Fechado) e reabrir | **Apagar** chamados |
| Buscar e filtrar os próprios chamados | Transferir para outra fila / mudar o tipo | Promover administradores, desativar contas |
| Avaliar chamados encerrados | Painel e relatório Excel/PDF das suas filas | Redefinir senha (gera senha temporária) |
| Alterar dados e senha em Minha conta | | |

- Um atendente que abre um pedido para **outra** fila acompanha esse chamado como solicitante.
- A **primeira conta criada** no sistema vira administrador.
- Mudanças de status, responsável e fila ficam registradas no histórico do chamado.
- Não há envio de e-mail: quem esquece a senha pede ao administrador para redefini-la.
  A pessoa entra com a senha temporária e é obrigada a criar uma nova.

## Servidor

- **[deploy/INSTALACAO-UBUNTU.md](deploy/INSTALACAO-UBUNTU.md)**: passo a passo da instalação
  (PostgreSQL, serviço `systemd` com Gunicorn, Nginx, backup diário e HTTPS).
- **[deploy/OPERACAO.md](deploy/OPERACAO.md)**: dia a dia depois de instalado — como funciona,
  tarefas do administrador, atualizar o sistema, backup e restauração, problemas comuns.

## Desenvolvimento local

Requisitos: Python 3.10+.

```bash
pip install -r requirements.txt pytest
python -m pytest tests          # testes (usam SQLite em memória, não precisam de PostgreSQL)
python -m tests.demo            # demonstração com dados de exemplo em http://127.0.0.1:5057
```

Contas da demonstração: `admin/admin123` (administrador), `carlos/carlos123` (atendente da T.I),
`marta/marta123` (atendente da Manutenção), `ana/ana12345` e `bruno/bruno123` (usuários).
`python -m tests.demo --limpo` começa sem contas.

Para rodar contra um PostgreSQL local: copie `config.example.ini` para `config.ini`, ajuste
`url`, `secret_key` e `anexos_pasta`, depois `python manage.py migrar` e `python run.py`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/modelos.py` | tabelas (usuários, filas, tipos de pedido, chamados, comentários, anexos) e valores fixos |
| `app/servicos.py` | regras do sistema: contas, filas, chamados, visibilidade, painel, relatório |
| `app/seguranca.py` | sessão, permissões e proteção CSRF |
| `app/anexos.py` | validação e gravação dos anexos em disco |
| `app/rotas/` | páginas: `auth` (login/cadastro), `conta`, `chamados`, `admin` |
| `app/templates/`, `app/static/` | HTML, CSS e JavaScript (sem build, sem CDN) |
| `migracoes/` | versões da estrutura do banco (Alembic) |
| `manage.py` | `migrar`, `criar-admin`, `tornar-admin` |
| `wsgi.py` | ponto de entrada do Gunicorn |
| `deploy/` | serviço systemd, Nginx, backup e guia de instalação |
| `tests/` | testes, dados de exemplo e modo demonstração |

### Mudar a estrutura do banco

Altere `app/modelos.py` e gere a migração:

```bash
python -m alembic revision --autogenerate -m "descrição da mudança"
python manage.py migrar
```

Filas e tipos de pedido são cadastrados pela tela **Filas**. Setores de origem (o setor de quem
pede), prioridades e status ficam em listas no início de `app/modelos.py`.

## Segurança

- Senhas guardadas só como hash (scrypt), mínimo de 8 caracteres com letras e números.
- Permissões verificadas no servidor a cada requisição: conta desativada ou rebaixada perde o acesso na hora.
- Formulários protegidos contra CSRF; cookies `HttpOnly`/`SameSite` (e `Secure` com HTTPS).
- Login bloqueado por 5 minutos após 5 senhas erradas (vale para todos os processos do Gunicorn).
- Anexos: só extensões da lista em `app/anexos.py`, gravados com nome aleatório;
  arquivos que não são imagem ou PDF são sempre baixados, nunca abertos no navegador.
- O sistema sempre mantém pelo menos um administrador ativo.
