# Instalação no Ubuntu Server

Requer Ubuntu 22.04 ou mais novo (Python 3.10+). A instalação de produção foi feita seguindo
este guia (com Python 3.14). Os comandos são executados com um usuário que tenha `sudo`.

Resultado final: **Nginx** (porta 80) → **Gunicorn** (serviço `ticket-manager`) → **PostgreSQL**.

| Onde | O quê |
|---|---|
| `/opt/ticket-manager` | código (clone deste repositório, branch `main`) e ambiente Python (`.venv/`) |
| `/etc/ticket-manager/config.ini` | configuração com a senha do banco (só root e o serviço leem) |
| `/var/lib/ticket-manager/anexos` | arquivos anexados aos chamados |
| `/var/backups/ticket-manager` | backups diários |

| Nome | O que é |
|---|---|
| `ticketapp` | usuário **do Linux** que roda o serviço (sem senha, sem login) |
| `ticket` | usuário **do PostgreSQL** dono do banco |
| `ticket_manager` | nome do banco de dados |

> Não use o seu próprio usuário do servidor para rodar o serviço, mesmo que ele se chame
> `ticket`: ele tem `sudo`. O serviço usa sempre o `ticketapp`.

Para o dia a dia depois de instalado (atualizar, backup, comandos úteis), veja
**[OPERACAO.md](OPERACAO.md)**.

## 1. Pacotes

```bash
sudo apt update
sudo apt install -y python3 python3-venv postgresql nginx git
sudo timedatectl set-timezone America/Sao_Paulo
```

## 2. Banco de dados

Use uma senha só com letras e números (evita ter que codificar caracteres na configuração). Anote.

```bash
sudo -u postgres createuser --pwprompt ticket
sudo -u postgres createdb --owner=ticket ticket_manager
```

## 3. Usuário do serviço e código

```bash
sudo useradd --system --home /opt/ticket-manager --shell /usr/sbin/nologin ticketapp
sudo git clone https://github.com/henrydk27/ticket-manager.git /opt/ticket-manager
sudo python3 -m venv /opt/ticket-manager/.venv
sudo /opt/ticket-manager/.venv/bin/pip install -r /opt/ticket-manager/requirements.txt
sudo mkdir -p /var/lib/ticket-manager/anexos
sudo chown -R ticketapp:ticketapp /var/lib/ticket-manager
```

Confira: `ls /opt/ticket-manager` deve mostrar `app`, `deploy`, `manage.py`, `requirements.txt`...

Se o repositório for privado, o `git clone` pede usuário e senha: no lugar da senha use um
**token de acesso pessoal** do GitHub (Settings → Developer settings → Personal access tokens).

## 4. Configuração

```bash
sudo mkdir -p /etc/ticket-manager
sudo cp /opt/ticket-manager/config.example.ini /etc/ticket-manager/config.ini
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copie o texto gerado
sudo nano /etc/ticket-manager/config.ini
```

Altere só estas duas linhas (o resto pode ficar como está):

```ini
url = postgresql+psycopg://ticket:SENHA_DO_BANCO@localhost:5432/ticket_manager
secret_key = TEXTO_GERADO_ACIMA
```

Se a senha do banco tiver `@`, `:` ou `/`, escreva `%40`, `%3A` ou `%2F` no lugar.
Para os avisos por e-mail, preencha também a seção `[email]` (veja [OPERACAO.md](OPERACAO.md#avisos-por-e-mail)); dá para fazer depois.
No nano: **Ctrl+O**, **Enter** para salvar, **Ctrl+X** para sair.

Proteja o arquivo:

```bash
sudo chown root:ticketapp /etc/ticket-manager/config.ini
sudo chmod 640 /etc/ticket-manager/config.ini
```

## 5. Criar as tabelas

```bash
cd /opt/ticket-manager
sudo -u ticketapp TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py migrar
```

Deve terminar com **"Banco atualizado."** (isso também confirma que a senha do banco está certa).

## 6. Serviço e Nginx

```bash
sudo cp /opt/ticket-manager/deploy/ticket-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ticket-manager
sudo systemctl status ticket-manager --no-pager     # deve aparecer "active (running)"

sudo cp /opt/ticket-manager/deploy/nginx-ticket-manager.conf /etc/nginx/sites-available/ticket-manager
sudo ln -s /etc/nginx/sites-available/ticket-manager /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx        # "syntax is ok" e "test is successful"

sudo ufw allow 'Nginx HTTP'    # se o firewall estiver ativo
hostname -I                    # mostra o IP do servidor
```

## 7. Primeiro acesso

Abra `http://IP-DO-SERVIDOR` num computador da rede e clique em **Crie sua conta**.

**A primeira conta criada é a de administrador** — crie a sua antes de divulgar o endereço.
As próximas entram como usuário comum; promova os técnicos em **Usuários**.

(Alternativa pelo terminal: `manage.py criar-admin LOGIN`, com o mesmo `sudo -u ticketapp
TICKET_MANAGER_CONFIG=...` do passo 5.)

## 8. Backup diário

Rode uma vez à mão para testar:

```bash
sudo bash /opt/ticket-manager/deploy/backup.sh
sudo ls -lh /var/backups/ticket-manager
```

Devem aparecer dois arquivos com a data de hoje: `banco_...dump` e `anexos_...tar.gz`.

Agende para todo dia às 2h30:

```bash
sudo crontab -e
```

(Se perguntar qual editor, escolha o `nano`.) Adicione no final a linha abaixo e salve:

```
30 2 * * * /bin/bash /opt/ticket-manager/deploy/backup.sh
```

Confira com `sudo crontab -l`. O script guarda os últimos 14 dias e apaga os mais antigos.
Para restaurar um backup, veja [OPERACAO.md](OPERACAO.md#restaurar-um-backup).

**Os backups ficam no mesmo disco do servidor.** Copie-os regularmente para outro lugar
(outro computador, HD externo ou nuvem) — se o disco falhar, eles vão junto.

## HTTPS (recomendado se houver acesso de fora da rede)

Com um domínio apontando para o servidor:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chamados.suaempresa.com.br
```

Depois, em `/etc/ticket-manager/config.ini`, defina `cookie_seguro = true` e rode
`sudo systemctl restart ticket-manager`.

## Problemas comuns na instalação

| Mensagem | Causa e solução |
|---|---|
| `Remote branch ticket-manager-web not found` / `.../web/requirements.txt` não existe | Comandos de uma versão antiga do guia. O código fica na branch `main`, na raiz. Use os comandos deste arquivo. |
| `destination path '/opt/ticket-manager' already exists` | Sobrou a pasta de uma tentativa anterior. Veja o conteúdo com `ls -la /opt/ticket-manager`; se só tiver `venv`/`.venv`, apague com `sudo rm -rf /opt/ticket-manager` e clone de novo. |
| `useradd: user 'ticketapp' already exists` | O usuário já foi criado antes. Pode seguir. |
| `502 Bad Gateway` no navegador | Serviço parado ou erro na configuração: `sudo journalctl -u ticket-manager -n 50 --no-pager`. |
| Erro de senha ao rodar `migrar` | Confira `url` em `[banco]`; caracteres especiais da senha precisam de codificação (`@` → `%40`). |
| Backup: `Permission denied` | Rode com `bash` na frente, como na linha do cron acima. |
| Anexo não salva | Dono de `/var/lib/ticket-manager/anexos` deve ser `ticketapp`: repita o `chown` do passo 3. |
| Upload "arquivo grande demais" | `client_max_body_size` no Nginx e `anexo_max_mb` no config.ini. |
