# Hospedar outra aplicação no mesmo servidor

Passo a passo para colocar uma **segunda aplicação web em Python** (Flask, Django, FastAPI...) no
mesmo servidor Ubuntu do Ticket Manager, com a mesma arquitetura:

```
Navegador → Nginx (porta 80) ─┬─ ticket.empresa…   → Gunicorn 127.0.0.1:8000 → Ticket Manager
                              └─ estoque.empresa…  → Gunicorn 127.0.0.1:8001 → nova aplicação
                                                                                  ↓
                                                                   PostgreSQL (um banco para cada)
```

As duas aplicações dividem o Nginx e o PostgreSQL, mas cada uma tem **o seu usuário do Linux,
a sua pasta, o seu banco, a sua porta interna e o seu serviço**. Assim uma não enxerga os
arquivos nem os dados da outra, e dá para parar, atualizar ou apagar uma sem mexer na outra.

> Se a aplicação foi feita por outra pessoa ou outra IA, confira antes a compatibilidade com o
> [CHECKLIST-NOVA-APLICACAO.md](CHECKLIST-NOVA-APLICACAO.md).

## Antes de começar: escolha os nomes

O exemplo deste guia usa uma aplicação chamada **estoque**. Troque pelos nomes da sua em todos os
comandos.

| O quê | Ticket Manager (já existe) | Nova aplicação (exemplo) |
|---|---|---|
| Nome curto | `ticket-manager` | `estoque` |
| Usuário do Linux que roda o serviço | `ticketapp` | `estoqueapp` |
| Pasta do código | `/opt/ticket-manager` | `/opt/estoque` |
| Configuração (senhas) | `/etc/ticket-manager/config.ini` | `/etc/estoque/` |
| Arquivos enviados pelos usuários | `/var/lib/ticket-manager` | `/var/lib/estoque` |
| Banco / usuário do banco | `ticket_manager` / `ticket` | `estoque` / `estoque` |
| Porta interna do Gunicorn | `8000` | **`8001`** (a próxima será `8002`...) |
| Serviço (systemd) | `ticket-manager` | `estoque` |
| Endereço no navegador | o atual | ex.: `http://estoque.SUAEMPRESA.lan` |

**Porta interna:** cada aplicação precisa de uma porta só dela. Ela só é usada dentro do servidor
(`127.0.0.1`): os usuários continuam acessando pela porta 80, e o Nginx decide para qual aplicação
mandar pelo **nome** digitado no navegador. Para ver as portas já em uso: `sudo ss -tlnp`.

**Endereço:** o jeito mais simples é dar um nome para cada aplicação no **DNS interno** da empresa
(o servidor de DNS do Windows/AD ou do roteador), apontando para o IP deste servidor. Evite nomes
terminados em `.local` (ficam lentos no Windows, como aconteceu com o `ticket.local`). Sem acesso
ao DNS, veja a [alternativa por porta](#alternativa-sem-dns-uma-porta-para-cada-aplicação).

## 1. Pacotes

Já estão instalados por causa do Ticket Manager. Se for um servidor novo:

```bash
sudo apt update
sudo apt install -y python3 python3-venv postgresql nginx git
sudo timedatectl set-timezone America/Sao_Paulo
```

## 2. Banco de dados

Um banco e um usuário do banco **só para a nova aplicação** (senha só com letras e números; anote):

```bash
sudo -u postgres createuser --pwprompt estoque
sudo -u postgres createdb --owner=estoque estoque
```

Confira: `sudo -u postgres psql -l` deve listar `ticket_manager` e `estoque`.

## 3. Usuário do serviço e código

```bash
sudo useradd --system --home /opt/estoque --shell /usr/sbin/nologin estoqueapp
sudo git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git /opt/estoque
sudo python3 -m venv /opt/estoque/.venv
sudo /opt/estoque/.venv/bin/pip install -r /opt/estoque/requirements.txt
sudo /opt/estoque/.venv/bin/pip install gunicorn      # se não estiver no requirements.txt
sudo mkdir -p /var/lib/estoque
sudo chown -R estoqueapp:estoqueapp /var/lib/estoque
```

O usuário `estoqueapp` não tem senha nem login: existe só para rodar o serviço. O código fica
com o dono `root` (o serviço lê, mas não altera), e só `/var/lib/estoque` aceita escrita.

## 4. Configuração (senhas fora do código)

Nunca deixe senha do banco ou chave secreta dentro do repositório. Coloque num arquivo em `/etc`:

```bash
sudo mkdir -p /etc/estoque
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # chave secreta: copie o texto gerado
sudo nano /etc/estoque/config.ini
```

O formato depende da aplicação. No padrão do Ticket Manager:

```ini
[banco]
url = postgresql+psycopg://estoque:SENHA_DO_BANCO@localhost:5432/estoque

[servidor]
secret_key = TEXTO_GERADO_ACIMA
atras_de_proxy = true
```

(Aplicações Django/FastAPI costumam ler variáveis de ambiente ou um arquivo `.env`: o caminho
continua sendo `/etc/estoque/`, só muda o nome do arquivo.)

Proteja o arquivo, para só o root e o serviço lerem:

```bash
sudo chown root:estoqueapp /etc/estoque/config.ini
sudo chmod 640 /etc/estoque/config.ini
```

## 5. Criar as tabelas

Rode o comando de migração da aplicação **como o usuário do serviço**:

```bash
cd /opt/estoque
sudo -u estoqueapp ESTOQUE_CONFIG=/etc/estoque/config.ini .venv/bin/python manage.py migrar
```

| Tipo de aplicação | Comando de migração (exemplos) |
|---|---|
| No padrão do Ticket Manager (Alembic) | `.venv/bin/python manage.py migrar` |
| Flask com Alembic puro | `.venv/bin/alembic upgrade head` |
| Django | `.venv/bin/python manage.py migrate` e `.venv/bin/python manage.py collectstatic` |

## 6. Serviço (systemd)

Crie o arquivo do serviço (é uma cópia do `ticket-manager.service`, com nomes e porta trocados):

```bash
sudo nano /etc/systemd/system/estoque.service
```

```ini
[Unit]
Description=Estoque (Gunicorn)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=estoqueapp
Group=estoqueapp
WorkingDirectory=/opt/estoque
Environment=ESTOQUE_CONFIG=/etc/estoque/config.ini
Environment=TZ=America/Sao_Paulo
ExecStart=/opt/estoque/.venv/bin/gunicorn wsgi:app \
    --bind 127.0.0.1:8001 --workers 3 --timeout 60 \
    --access-logfile - --error-logfile -
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/estoque

[Install]
WantedBy=multi-user.target
```

O que muda conforme a aplicação é só o `wsgi:app` (onde está o objeto da aplicação):

| Tipo | No lugar de `wsgi:app` |
|---|---|
| Flask com `wsgi.py` (como o nosso) | `wsgi:app` |
| Flask com `app.py` e `app = Flask(...)` | `app:app` |
| Django (projeto `meusite`) | `meusite.wsgi:application` |
| FastAPI (`main.py`, `app = FastAPI()`) | `main:app -k uvicorn.workers.UvicornWorker` (instale `uvicorn` no `.venv`) |

Ligue e confira:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now estoque
sudo systemctl status estoque --no-pager          # "active (running)"
curl -I http://127.0.0.1:8001                     # deve responder (200, 302...)
```

## 7. Nginx

### 7.1 Deixe o Ticket Manager como o site padrão

Hoje o Ticket Manager responde a qualquer nome (`server_name _`). Com duas aplicações, ele
continua sendo o padrão (quem digitar só o IP cai nele), e a nova responde só pelo nome dela:

```bash
sudo nano /etc/nginx/sites-available/ticket-manager
```

Troque a linha `listen 80;` por:

```nginx
    listen 80 default_server;
```

### 7.2 Site da nova aplicação

```bash
sudo nano /etc/nginx/sites-available/estoque
```

```nginx
server {
    listen 80;
    server_name estoque.SUAEMPRESA.lan;     # o nome cadastrado no DNS

    client_max_body_size 20m;               # tamanho máximo de envio de arquivos

    # Arquivos estáticos direto pelo Nginx (ajuste para a pasta da aplicação;
    # no Django é a pasta do STATIC_ROOT)
    location /static/ {
        alias /opt/estoque/app/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Ative e recarregue (o `nginx -t` confere se está tudo certo antes de aplicar):

```bash
sudo ln -s /etc/nginx/sites-available/estoque /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 8. Endereço (DNS)

No DNS interno, crie um registro **A** com o nome `estoque.SUAEMPRESA.lan` apontando para o IP
deste servidor (o mesmo do Ticket Manager). Teste num computador da rede:

```
nslookup estoque.SUAEMPRESA.lan
```

Deve responder o IP do servidor. Depois abra `http://estoque.SUAEMPRESA.lan`.

Para testar antes de mexer no DNS, num único computador Windows: abra o Bloco de Notas **como
administrador**, edite `C:\Windows\System32\drivers\etc\hosts` e acrescente a linha
`IP-DO-SERVIDOR  estoque.SUAEMPRESA.lan`.

### Alternativa sem DNS: uma porta para cada aplicação

Se não houver como cadastrar nomes, a nova aplicação pode responder numa porta diferente:
no arquivo do passo 7.2, troque `listen 80;` por `listen 8080;` e `server_name` por `_`. O
endereço fica `http://IP-DO-SERVIDOR:8080`. Libere a porta no firewall:

```bash
sudo ufw allow 8080/tcp      # só se o firewall estiver ativo (sudo ufw status)
```

## 9. Backup

Copie o script do Ticket Manager e troque os nomes:

```bash
sudo cp /opt/ticket-manager/deploy/backup.sh /usr/local/bin/backup-estoque.sh
sudo nano /usr/local/bin/backup-estoque.sh
```

Troque `ticket-manager` por `estoque` nas pastas e `ticket_manager` por `estoque` no `pg_dump`.
Teste e agende (2h45, depois do backup do Ticket Manager):

```bash
sudo bash /usr/local/bin/backup-estoque.sh && sudo ls -lh /var/backups/estoque
sudo crontab -e
```

```
45 2 * * * /bin/bash /usr/local/bin/backup-estoque.sh
```

## 10. Atualizar a aplicação depois

```bash
cd /opt/estoque
sudo git pull
sudo .venv/bin/pip install -r requirements.txt
# migração do banco, se houver (passo 5)
sudo systemctl restart estoque
```

## Comandos do dia a dia

| Para | Comando |
|---|---|
| Ver se está rodando | `sudo systemctl status estoque` |
| Reiniciar | `sudo systemctl restart estoque` |
| Ver os erros (logs) | `sudo journalctl -u estoque -n 100 --no-pager` |
| Acompanhar os logs ao vivo | `sudo journalctl -u estoque -f` |
| Logs do Nginx | `sudo tail -n 50 /var/log/nginx/error.log` |
| Portas em uso | `sudo ss -tlnp` |

## Problemas comuns

| Sintoma | Causa provável e o que fazer |
|---|---|
| **502 Bad Gateway** | O serviço não está rodando ou está em outra porta. `sudo systemctl status estoque` e `journalctl -u estoque`; confira se a porta do `proxy_pass` é a mesma do `--bind`. |
| O nome novo abre o **Ticket Manager** | O `server_name` não bate com o nome digitado, ou o site novo não foi ativado (`ls /etc/nginx/sites-enabled`). Rode `sudo nginx -t` e `reload`. |
| `Address already in use` ao iniciar | A porta já é de outra aplicação: escolha outra (8002...) no serviço e no Nginx. |
| Página sem estilo (CSS/imagens 404) | O `alias` do `/static/` aponta para a pasta errada (termine com `/`), ou faltou o `collectstatic` (Django). |
| `Permission denied` nos logs | A aplicação tentou escrever fora de `/var/lib/estoque`. Mude a pasta na configuração ou acrescente-a em `ReadWritePaths` e rode `daemon-reload` + `restart`. |
| `password authentication failed` | Senha ou usuário do banco errados no `config.ini` (passo 4). |
| `ModuleNotFoundError` | Faltou instalar dependência no `.venv`: `sudo /opt/estoque/.venv/bin/pip install -r requirements.txt`. |
| O nome não abre em nenhum computador | O DNS ainda não tem o registro (teste com `nslookup`) ou o firewall bloqueia a porta. |

## Resumo: o que copiar e o que trocar

1. **Banco**: `createuser` + `createdb` com o nome novo.
2. **Usuário do Linux** `NOMEapp`, pasta `/opt/NOME`, `.venv`, dependências e `gunicorn`.
3. **Configuração** em `/etc/NOME/` com permissão `640`.
4. **Migração** do banco como `NOMEapp`.
5. **Serviço** `/etc/systemd/system/NOME.service` com **porta nova** e `ReadWritePaths=/var/lib/NOME`.
6. **Nginx**: Ticket Manager com `default_server`; site novo com `server_name` próprio e `proxy_pass` na porta nova.
7. **DNS**: registro do nome novo apontando para o servidor.
8. **Backup** no cron.
