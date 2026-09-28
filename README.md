# Ticket Manager Web

Sistema de chamados acessado pelo navegador, para **qualquer setor** da empresa: T.I,
Manutenção, RH, Compras... Feito em Python (Flask) com banco **PostgreSQL**, para rodar num
servidor **Ubuntu**. Refeito do zero a partir das funções da versão Lazarus.

## Como funciona

- Ao abrir um chamado, a pessoa escolhe **para qual setor** é o pedido e, em seguida, o
  **funcionário** desse setor que vai atender.
- Na tela **Usuários**, o administrador define o setor de cada pessoa e marca quem
  **atende chamados**. Só essas pessoas aparecem na lista de funcionários.
- **Todos que atendem o setor veem os chamados dele** e podem assumir (se o colega faltar,
  por exemplo) ou **encaminhar** para outra pessoa ou outro setor.

| Todos | Quem atende chamados (do seu setor) | Administradores |
|---|---|---|
| Criar a própria conta | Ver os chamados do setor | Ver e atender **todos** os chamados |
| Abrir chamado para um setor e funcionário, com anexos | Assumir um chamado do setor | Definir setor, quem atende e perfil de cada conta |
| Comentar e anexar arquivos | Mudar status (Aberto, Em andamento, Aguardando usuário, Fechado) e reabrir | **Apagar** chamados |
| Buscar e filtrar os próprios chamados | Encaminhar para outra pessoa ou outro setor | Desativar contas e redefinir senhas |
| Avaliar chamados encerrados | Painel e relatório Excel/PDF do setor | |
| Alterar nome, e-mail e senha em Minha conta | | |

- Quem atende e abre um pedido para **outro** setor acompanha esse chamado como solicitante.
- A **primeira conta criada** no sistema vira administrador.
- O setor de cada pessoa só é alterado pelo administrador (é ele que define o que ela vê).
- Mudanças de status, responsável e setor ficam registradas no histórico do chamado.
- **Avisos por e-mail** (chamado novo, encaminhado, respostas, status e encerramento), pelo
  e-mail da empresa via SMTP. Configuração em [deploy/OPERACAO.md](deploy/OPERACAO.md#avisos-por-e-mail).
- Quem esquece a senha pede ao administrador para redefini-la; a pessoa entra com a senha
  temporária e é obrigada a criar uma nova.

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

Contas da demonstração: `admin/admin123` (administrador, T.I), `carlos/carlos123` (T.I),
`marta/marta123` (Manutenção) e `rita/rita1234` (RH) atendem chamados; `ana/ana12345` e
`bruno/bruno123` são usuários comuns.
`python -m tests.demo --limpo` começa sem contas.

Para rodar contra um PostgreSQL local: copie `config.example.ini` para `config.ini`, ajuste
`url`, `secret_key` e `anexos_pasta`, depois `python manage.py migrar` e `python run.py`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/modelos.py` | tabelas (usuários, chamados, comentários, anexos) e valores fixos (setores, status) |
| `app/servicos.py` | regras do sistema: contas, quem atende, chamados, visibilidade, painel, relatório |
| `app/seguranca.py` | sessão, permissões e proteção CSRF |
| `app/anexos.py` | validação e gravação dos anexos em disco |
| `app/notificacoes.py`, `app/correio.py` | quem recebe cada aviso e o envio por SMTP em segundo plano |
| `app/rotas/` | páginas: `auth` (login/cadastro), `conta`, `chamados`, `admin` |
| `app/templates/`, `app/static/` | HTML, CSS e JavaScript (sem build, sem CDN) |
| `migracoes/` | versões da estrutura do banco (Alembic) |
| `manage.py` | `migrar`, `criar-admin`, `tornar-admin`, `testar-email` |
| `wsgi.py` | ponto de entrada do Gunicorn |
| `deploy/` | serviço systemd, Nginx, backup e guia de instalação |
| `tests/` | testes, dados de exemplo e modo demonstração |

### Mudar a estrutura do banco

Altere `app/modelos.py` e gere a migração:

```bash
python -m alembic revision --autogenerate -m "descrição da mudança"
python manage.py migrar
```

Setores, prioridades e status ficam em listas no início de `app/modelos.py`. Quem atende cada
setor é definido na tela **Usuários**.

## Segurança

- Senhas guardadas só como hash (scrypt), mínimo de 8 caracteres com letras e números.
- Permissões verificadas no servidor a cada requisição: conta desativada ou rebaixada perde o acesso na hora.
- Formulários protegidos contra CSRF; cookies `HttpOnly`/`SameSite` (e `Secure` com HTTPS).
- Login bloqueado por 5 minutos após 5 senhas erradas (vale para todos os processos do Gunicorn).
- Anexos: só extensões da lista em `app/anexos.py`, gravados com nome aleatório;
  arquivos que não são imagem ou PDF são sempre baixados, nunca abertos no navegador.
- O sistema sempre mantém pelo menos um administrador ativo.
