# Ticket Manager Web

Sistema de chamados e inventário de TI acessado pelo navegador, para **qualquer setor** da
empresa: T.I, Manutenção, RH, Compras... Feito em Python (Flask) com banco **PostgreSQL**, para
rodar num servidor **Ubuntu**. Refeito do zero a partir das funções da versão Lazarus.

Apresentação com prints de todas as telas: [docs/APRESENTACAO.md](docs/APRESENTACAO.md).

## Chamados

- Ao abrir um chamado, a pessoa escolhe **para qual setor** é o pedido e, em seguida, o
  **funcionário** desse setor que vai atender.
- Na tela **Usuários**, o administrador define o setor de cada pessoa e marca quem
  **atende chamados**. Só essas pessoas aparecem na lista de funcionários.
- **Todos que atendem o setor veem os chamados dele** e podem assumir (se o colega faltar,
  por exemplo) ou **encaminhar** para outra pessoa ou outro setor.

Níveis de acesso (perfil): **Usuário**, **Supervisor** e **Administrador**.

| | Chamados | Painel | Relatório | Documentos | Inventário e Usuários |
|---|---|---|---|---|---|
| **Usuário** | os que abriu (+ os do setor, se atende) | sim | — | — | — |
| **Supervisor** | os do seu setor + os que abriu | sim | do seu setor | consulta | — |
| **Administrador** | todos | todos os setores (com filtro) | todos os setores | consulta e publica | sim |

As **telas** dependem só do nível de acesso. **Atende chamados** é independente: define quem
aparece na lista de funcionários ao abrir um chamado e quem atende (assume, muda status,
encaminha) os chamados do próprio setor. O supervisor vê os chamados do setor mesmo sem atender.
No **Painel**, quem atende e o supervisor veem o setor; o usuário que não atende vê os chamados
que abriu.

Quem **atende chamados** do setor (qualquer nível) assume, muda status (Aberto, Em andamento,
Aguardando usuário, Fechado), reabre e encaminha para outra pessoa ou outro setor. Todos abrem
chamados com anexos, comentam, avaliam os encerrados e alteram nome, e-mail e senha em Minha conta.
Só o administrador define setor, nível e quem atende, cadastra, **edita** (nome, usuário, e-mail)
e desativa contas, libera nova senha e **apaga** chamados, equipamentos e contas desativadas sem
histórico. Tudo isso fica na tela **Editar** de cada conta.

- Quem atende e abre um pedido para **outro** setor acompanha esse chamado como solicitante.
- A **primeira conta criada** no sistema vira administrador.
- O setor de cada pessoa só é alterado pelo administrador (é ele que define o que ela vê).
- Mudanças de status, responsável e setor ficam registradas no histórico do chamado.
- O administrador pode **corrigir o texto de um comentário**; o histórico mostra quem editou e quando.
- **Painel:** em aberto, sem responsável, abertos e encerrados no período, tempo médio até
  encerrar e gráficos por status, responsável, setor, prioridade, avaliações e mês. O tempo
  médio conta **só o expediente** (segunda a sexta, das 7h às 18h; ajuste em
  `EXPEDIENTE_INICIO`, `EXPEDIENTE_FIM` e `DIAS_EXPEDIENTE` em `app/servicos.py`).
  **Relatório** do período em Excel ou PDF.

## Inventário de TI

Só para administradores: equipamentos cadastrados com o **nº de
patrimônio que já têm** (editável e único), tipo, marca/modelo, série, configuração do
computador e rede (hostname, IP, MAC). Cada equipamento fica com um **usuário** e/ou um
**setor**, e toda troca de usuário, setor ou situação vai para o **histórico**, com data e quem
fez. A lista tem busca, filtros e **exportação para Excel**; o patrimônio é ordenado pelo
número (2, 99, 100...).

## Documentos

Termos, regras, procedimentos e formulários internos da empresa. Supervisores e
administradores consultam, abrem (PDF e imagens no navegador) e baixam; só administradores
cadastram, trocam o arquivo e apagam. Cada documento tem título, categoria, descrição opcional e um arquivo
(PDF, Word, Excel, PowerPoint, texto ou imagem), guardado na mesma pasta dos anexos.

## Outros

- **Avisos por e-mail** (chamado novo, encaminhado, respostas, status e encerramento), pelo
  servidor de e-mail da empresa via SMTP. Configuração em [deploy/OPERACAO.md](deploy/OPERACAO.md#avisos-por-e-mail).
- **Modo claro/escuro e tema de cor:** botões no canto da tela. O tema pinta a tela inteira
  (fundo, cartões, bordas, botões e gráficos): Padrão (o visual original) ou uma de 8 cores
  (Azul, Petróleo, Verde, Roxo, Rosa, Vermelho, Laranja, Grafite), com intensidade de 1 (Suave)
  a 5 (Intensa). As cores de situação e de alerta não mudam. Todas as combinações têm contraste
  conferido nos dois modos. A escolha fica guardada em cada navegador.
- O administrador também **cadastra contas** (ex.: para atribuir equipamentos a quem ainda não
  tem conta). A conta nasce sem senha: no primeiro acesso a pessoa digita só o usuário e cria a
  própria senha (prazo de 7 dias).
- **Esqueceu a senha?** Na tela de login, **Solicitar nova senha** manda um e-mail ao CPD. O
  administrador confere com a pessoa e clica em **Liberar nova senha**; ela entra digitando só o
  usuário e cria a senha nova.
- Funciona no computador e no celular; ninguém precisa instalar nada.

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
`bruno/bruno123` são usuários comuns. A demonstração já vem com chamados e equipamentos.
`python -m tests.demo --limpo` começa sem contas.

Para rodar contra um PostgreSQL local: copie `config.example.ini` para `config.ini`, ajuste
`url`, `secret_key` e `anexos_pasta`, depois `python manage.py migrar` e `python run.py`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/modelos.py` | tabelas (usuários, chamados, comentários, anexos, equipamentos, histórico) e valores fixos |
| `app/servicos.py` | regras do sistema: contas, quem atende, chamados, visibilidade, painel, relatório |
| `app/seguranca.py` | sessão, permissões e proteção CSRF |
| `app/anexos.py` | validação e gravação dos anexos em disco |
| `app/inventario.py`, `app/rotas/inventario.py` | inventário de TI: equipamentos, atribuição e histórico |
| `app/documentos.py`, `app/rotas/documentos.py` | documentos internos (termos, regras, procedimentos) |
| `app/notificacoes.py`, `app/correio.py` | quem recebe cada aviso e o envio por SMTP em segundo plano |
| `app/rotas/` | páginas: `auth` (login/cadastro), `conta`, `chamados`, `admin` (painel, relatório, usuários), `inventario` |
| `app/templates/`, `app/static/` | HTML, CSS e JavaScript (sem build, sem CDN); `tema.js` aplica claro/escuro e a cor |
| `app/temas.py` | temas de cor (cor × intensidade × claro/escuro); gera `static/cores.css` (`python -m app.temas`) |
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

Setores, prioridades, status, tipos de equipamento e situações ficam em listas no início de
`app/modelos.py`. Para incluir ou mudar uma cor do tema, edite `CORES` em `app/temas.py` e rode
`python -m app.temas` (o comando aponta combinações sem contraste; um teste confere o `cores.css`). Quem atende cada setor é definido na tela **Usuários**.

### Arquivos estáticos

Sempre gere o endereço de CSS, JS e imagens com `url_for('static', filename=...)`: o sistema
acrescenta `?v=<data do arquivo>` automaticamente, e assim os navegadores baixam a versão nova
depois de cada atualização (o Nginx guarda esses arquivos em cache por 7 dias).

## Segurança

- Senhas guardadas só como hash (scrypt), mínimo de 8 caracteres com letras e números.
- Permissões verificadas no servidor a cada requisição: conta desativada ou rebaixada perde o acesso na hora.
- Formulários protegidos contra CSRF; cookies `HttpOnly`/`SameSite` (e `Secure` com HTTPS).
- Login bloqueado por 5 minutos após 5 senhas erradas (vale para todos os processos do Gunicorn).
- Anexos: só extensões da lista em `app/anexos.py`, gravados com nome aleatório;
  arquivos que não são imagem ou PDF são sempre baixados, nunca abertos no navegador.
- O sistema sempre mantém pelo menos um administrador ativo.
