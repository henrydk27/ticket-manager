# Checklist de compatibilidade de uma nova aplicação

Use quando uma aplicação foi feita **fora daqui** (por outra pessoa ou outra IA) e precisa ser
hospedada no nosso servidor do mesmo jeito que o Ticket Manager (veja
[HOSPEDAR-OUTRA-APLICACAO.md](HOSPEDAR-OUTRA-APLICACAO.md)).

Como usar:

1. Copie o texto da seção **[Texto para colar na outra IA](#texto-para-colar-na-outra-ia)** e cole na
   conversa da IA que fez a aplicação (com o projeto aberto ou anexado, para ela olhar o código).
2. Peça para ela **corrigir no projeto** o que estiver marcado como "precisa ajuste".
3. Confira as respostas com a [lista rápida](#lista-rápida-para-você-conferir) abaixo.
4. Se o projeto ainda não está no GitHub, siga [Subir o projeto para o GitHub](#subir-o-projeto-para-o-github).
5. Com as respostas em mãos, monte o servidor pelo guia de hospedagem.

---

## Texto para colar na outra IA

```text
Preciso hospedar esta aplicação num servidor da empresa que já roda outra aplicação web.
Analise o código deste projeto e me diga, item por item, se ele é compatível com o ambiente
abaixo. Para cada item responda: OK, PRECISA AJUSTE (diga exatamente o que mudar e faça a
alteração no código) ou NÃO SE APLICA. No final, preencha a ficha de instalação.

=== AMBIENTE DE DESTINO ===
- Servidor Ubuntu Server (LTS), sem Docker, sem interface gráfica. Python 3 do sistema com venv.
- Acesso só pela rede interna da empresa, por HTTP (porta 80). Sem HTTPS por enquanto.
- Nginx na frente como proxy reverso: recebe o acesso pelo nome da aplicação (ex.:
  estoque.empresa.lan) e repassa para 127.0.0.1:<porta interna>. O Nginx serve sozinho a pasta
  de arquivos estáticos (/static/). Já existe outra aplicação no mesmo Nginx.
- A aplicação roda com Gunicorn (vários workers) como serviço do systemd, com um usuário do Linux
  próprio, sem login e sem sudo.
- O serviço roda com ProtectSystem=strict: só consegue gravar em UMA pasta de dados
  (/var/lib/<nome>). A pasta do código (/opt/<nome>) é somente leitura para ela.
- Banco PostgreSQL no mesmo servidor, com um banco e um usuário só desta aplicação.
- Código instalado com "git clone" do GitHub em /opt/<nome>; atualização com "git pull".
- Senhas e configurações ficam FORA do repositório, num arquivo em /etc/<nome>/ (ou variáveis
  de ambiente definidas no serviço), legível só pelo usuário do serviço.
- Fuso horário America/Sao_Paulo. Interface em português.
- Tarefas agendadas rodam pelo cron do servidor, chamando um comando da aplicação.
- E-mail (se houver) por SMTP interno da empresa: porta 587 com STARTTLS, certificado próprio
  (precisa poder desligar a verificação do certificado), ou porta 25 sem autenticação.
- Backup diário: pg_dump do banco + compactação da pasta de dados.

=== CHECKLIST ===
1. Linguagem e framework
   1.1 Qual linguagem e versão mínima? (precisa ser Python 3.10 ou mais novo)
   1.2 Qual framework? (Flask, Django, FastAPI, outro)
   1.3 Qual é o ponto de entrada para o Gunicorn, no formato modulo:objeto?
       (ex.: wsgi:app, meusite.wsgi:application). Se for ASGI (FastAPI), diga e confirme que
       funciona com "gunicorn -k uvicorn.workers.UvicornWorker".
   1.4 Confirme que em produção NÃO usa o servidor de desenvolvimento (app.run, runserver,
       debug=True) e que o modo debug fica desligado.

2. Dependências
   2.1 Existe requirements.txt com todas as bibliotecas (de preferência com versões)?
       Se não existir, crie. Inclua gunicorn (e uvicorn, se for ASGI) e o driver do PostgreSQL.
   2.2 Precisa de algum pacote do sistema (apt)? Ex.: libpq-dev, wkhtmltopdf, poppler,
       tesseract, fontes. Liste.
   2.3 Precisa de Node.js/npm para compilar o front-end? Se sim, os arquivos já compilados
       podem ficar no repositório? (no servidor não instalamos Node)
   2.4 Usa algo que só existe no Windows (caminhos C:\, .exe, pywin32, COM)? Liste.

3. Banco de dados
   3.1 Usa PostgreSQL? Se usa SQLite ou outro, ajuste para PostgreSQL.
   3.2 A conexão (endereço, usuário, senha, nome do banco) vem da configuração externa,
       e não está escrita no código?
   3.3 Como as tabelas são criadas e atualizadas? (Alembic, migrations do Django, comando
       próprio). Qual é o comando exato? Ele pode ser rodado de novo sem perder dados?
   3.4 A aplicação cria tabelas sozinha ao iniciar (create_all)? Com vários workers isso
       pode dar conflito: prefira um comando de migração separado.

4. Configuração e segredos
   4.1 Liste TODAS as configurações necessárias (nome da variável ou chave, para que serve,
       exemplo de valor). Ex.: URL do banco, chave secreta, e-mail.
   4.2 Existe um arquivo de exemplo (.env.example ou config.example.ini) no repositório?
       Se não, crie.
   4.3 Confirme que não há senha, token ou chave real no código nem no histórico do Git.
   4.4 A chave secreta (SECRET_KEY) vem da configuração, e não é fixa no código?

5. Arquivos e pastas
   5.1 Onde a aplicação GRAVA arquivos? (uploads, anexos, relatórios gerados, logs, cache,
       banco SQLite, sessões). Todos esses caminhos precisam ser configuráveis para ficar
       em /var/lib/<nome>. Ajuste o que estiver fixo dentro da pasta do código.
   5.2 Logs: escreva na saída padrão (stdout/stderr), que o systemd guarda. Não grave log
       em arquivo dentro da pasta do código.
   5.3 Arquivos estáticos (CSS, JS, imagens): qual a pasta no projeto e o endereço (/static/)?
       No Django, informe o STATIC_ROOT e confirme o comando collectstatic.
   5.4 Qual o tamanho máximo de arquivo que os usuários enviam? (para configurar o Nginx)

6. Funcionamento atrás do Nginx
   6.1 A aplicação funciona atrás de proxy reverso? Ela precisa respeitar os cabeçalhos
       X-Forwarded-For e X-Forwarded-Proto (no Flask: ProxyFix; no Django: ALLOWED_HOSTS e
       CSRF_TRUSTED_ORIGINS com o nome da aplicação).
   6.2 Os links e redirecionamentos usam caminhos relativos ou o nome do site, e não
       "localhost:5000" ou um IP fixo?
   6.3 Ela roda na raiz do site ("/"), e não numa subpasta?
   6.4 Cookies com "Secure" obrigatório quebram sem HTTPS: isso precisa ser configurável.
   6.5 Usa WebSocket ou Server-Sent Events? (precisa de configuração extra no Nginx)

7. Vários workers do Gunicorn
   7.1 A aplicação guarda estado na memória do processo (sessões, filas, cache, contadores)?
       Com vários workers cada um tem a sua memória: o estado deve ficar no banco ou em
       cookie assinado.
   7.2 Ela inicia tarefas em segundo plano ou agendadores dentro do processo (APScheduler,
       threads com loop, Celery beat)? Com vários workers isso roda repetido. Troque por um
       comando de linha (ex.: "python manage.py enviar-avisos") para o cron chamar.
   7.3 Alguma requisição demora mais de 60 segundos? (relatórios pesados, importações)

8. Usuários e primeiro acesso
   8.1 Como é criado o primeiro administrador? (comando, tela de cadastro, usuário padrão)
   8.2 Existe usuário e senha padrão no código? Se sim, remova ou obrigue a troca.

9. Integrações
   9.1 Envia e-mail? Por qual biblioteca? O servidor SMTP, porta, segurança e a opção de
       não verificar o certificado são configuráveis?
   9.2 Acessa algum serviço da internet ou API externa? Qual, e precisa de chave?
   9.3 Lê ou grava em pastas da rede (compartilhamento Windows), outro banco ou outro sistema?

10. Git e GitHub
   10.1 Existe .gitignore cobrindo: .venv/venv, __pycache__, .env, arquivos de banco local
        (*.db, *.sqlite3), pastas de upload, logs, node_modules?
   10.2 O repositório tem arquivos grandes ou que não deveriam ir (backups, planilhas com
        dados reais, .exe, .zip)? Liste.
   10.3 Existe README com como rodar localmente e como instalar?

11. Testes e demonstração
   11.1 Existem testes automáticos? Qual comando roda?
   11.2 Dá para rodar localmente com dados de exemplo, sem o banco de produção?

=== FICHA DE INSTALAÇÃO (preencha no final) ===
- Nome curto sugerido para a aplicação (minúsculas, sem espaço):
- Versão mínima do Python:
- Pacotes apt necessários:
- Comando de instalação das dependências:
- Ponto de entrada do Gunicorn (modulo:objeto) e opções extras:
- Configurações necessárias (lista com exemplo de cada uma, sem valores reais):
- Onde fica o arquivo de configuração e como ele é lido (arquivo ou variáveis de ambiente):
- Comando para criar/atualizar as tabelas:
- Comando para criar o primeiro administrador:
- Pasta dos arquivos estáticos e endereço público:
- Pastas onde a aplicação grava (devem ficar em /var/lib/<nome>):
- Tamanho máximo de envio de arquivos:
- Tarefas agendadas (comando e frequência sugerida):
- Comando para rodar os testes:
- Ajustes que você fez no código para ficar compatível (lista):
```

---

## Lista rápida para você conferir

Quando a outra IA responder, confira se estes pontos ficaram **OK**. São os que mais costumam
dar problema na instalação:

| ✔ | Ponto | Por que importa aqui |
|---|---|---|
| ☐ | É Python 3.10+ e tem `requirements.txt` com `gunicorn` | O servidor roda Python + Gunicorn |
| ☐ | Tem um ponto de entrada `modulo:objeto` | É o que vai no arquivo do serviço |
| ☐ | Usa PostgreSQL (não SQLite) | Mesmo banco e mesmo backup do Ticket Manager |
| ☐ | Tem comando de migração separado | Rodamos a cada atualização, como o `manage.py migrar` |
| ☐ | Senhas e chave secreta vêm de fora do código | Ficam em `/etc/<nome>/`, fora do GitHub |
| ☐ | Tem arquivo de exemplo da configuração | É dele que montamos o arquivo do servidor |
| ☐ | Grava arquivos só numa pasta configurável | O serviço só pode escrever em `/var/lib/<nome>` |
| ☐ | Funciona atrás do Nginx, sem `localhost:5000` fixo | O acesso chega pelo Nginx com o nome da aplicação |
| ☐ | Não tem agendador dentro do processo | Com vários workers rodaria repetido; usamos o cron |
| ☐ | Não precisa de Node/Windows no servidor | Não temos isso instalado |
| ☐ | Tem `.gitignore` e nenhum segredo no Git | O código vai para o GitHub |
| ☐ | Sabe como criar o primeiro administrador | Primeiro acesso depois de instalar |

Se algum item depender de algo que o nosso ambiente não tem (Docker, Node no servidor, Windows,
outro banco), dá para resolver, mas a instalação muda: traga a resposta antes de começar.

---

## Subir o projeto para o GitHub

Se a aplicação ainda **não** está no GitHub (está só numa pasta no computador):

1. No GitHub, crie um repositório **novo e vazio** (sem README, sem .gitignore), de preferência
   **privado**. Ex.: `SEU_USUARIO/estoque`.
2. No computador, abra o terminal na pasta do projeto e confira que existe o `.gitignore`
   (item 10.1 do checklist) **antes** do primeiro commit, para não subir senhas nem o `.venv`.
3. Rode:

```bash
git init -b main
git add .
git status
```

4. Leia a lista do `git status`: **não pode aparecer** `.env`, `.venv`, arquivos `.db`/`.sqlite3`,
   pastas de upload nem planilhas com dados reais. Se aparecer, acrescente ao `.gitignore`,
   rode `git rm -r --cached NOME` e `git add .` de novo.
5. Faça o primeiro commit e envie:

```bash
git commit -m "Primeira versão"
git remote add origin https://github.com/SEU_USUARIO/estoque.git
git push -u origin main
```

Se o `git push` pedir senha, use um **token de acesso pessoal** do GitHub (Settings → Developer
settings → Personal access tokens) no lugar da senha. O mesmo token serve no servidor para o
`git clone` de um repositório privado.

Se a aplicação **já está** no GitHub, confira só os passos 2 e 4 (nenhum segredo no repositório).
Se algum segredo já foi enviado, troque a senha/chave: apagar o arquivo depois não tira ele do
histórico.
