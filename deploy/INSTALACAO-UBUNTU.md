# Instalação no Ubuntu Server

Testado para Ubuntu 22.04 / 24.04. Os comandos são executados como um usuário com `sudo`.

Resultado final: **Nginx** (porta 80) → **Gunicorn** (serviço `ticket-manager`) → **PostgreSQL**.

| Onde | O quê |
|---|---|
| `/opt/ticket-manager` | código (clone do repositório) e ambiente Python (`.venv/`) |
| `/etc/ticket-manager/config.ini` | configuração com senha do banco (só root e o serviço leem) |
| `/var/lib/ticket-manager/anexos` | arquivos anexados aos chamados |
| `/var/backups/ticket-manager` | backups diários |

## 1. Pacotes

```bash
sudo apt update
sudo apt install -y python3 python3-venv postgresql nginx git
sudo timedatectl set-timezone America/Sao_Paulo
```

## 2. Banco de dados

```bash
sudo -u postgres createuser --pwprompt ticket        # digite uma senha forte e anote
sudo -u postgres createdb --owner=ticket ticket_manager
```

## 3. Usuário do sistema e código

```bash
sudo useradd --system --home /opt/ticket-manager --shell /usr/sbin/nologin ticket
sudo git clone https://github.com/henrydk27/ticket-manager.git /opt/ticket-manager
sudo python3 -m venv /opt/ticket-manager/.venv
sudo /opt/ticket-manager/.venv/bin/pip install -r /opt/ticket-manager/requirements.txt
sudo mkdir -p /var/lib/ticket-manager/anexos
sudo chown -R ticket:ticket /var/lib/ticket-manager
```

## 4. Configuração

```bash
sudo mkdir -p /etc/ticket-manager
sudo cp /opt/ticket-manager/config.example.ini /etc/ticket-manager/config.ini
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copie o resultado
sudo nano /etc/ticket-manager/config.ini
```

Preencha:
- `url` em `[banco]` com a senha criada no passo 2;
- `secret_key` com o valor gerado acima.

Depois, proteja o arquivo:

```bash
sudo chown root:ticket /etc/ticket-manager/config.ini
sudo chmod 640 /etc/ticket-manager/config.ini
```

## 5. Criar as tabelas

```bash
cd /opt/ticket-manager
sudo -u ticket TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py migrar
```

## 6. Serviço e Nginx

```bash
sudo cp /opt/ticket-manager/deploy/ticket-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ticket-manager
sudo systemctl status ticket-manager        # deve aparecer "active (running)"

sudo cp /opt/ticket-manager/deploy/nginx-ticket-manager.conf /etc/nginx/sites-available/ticket-manager
sudo ln -s /etc/nginx/sites-available/ticket-manager /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Se o firewall estiver ativo: `sudo ufw allow 'Nginx HTTP'`.

## 7. Primeiro acesso

Abra `http://IP-DO-SERVIDOR` e clique em **Crie sua conta**. **A primeira conta criada é a
de administrador.** As próximas entram como usuário comum; promova os técnicos em **Usuários**.

(Alternativa pelo terminal: `manage.py criar-admin LOGIN`, com as mesmas variáveis do passo 5.)

## 8. Backup diário

```bash
sudo crontab -e
# adicione a linha:
30 2 * * * /opt/ticket-manager/deploy/backup.sh
```

Para restaurar:

```bash
sudo -u postgres pg_restore --clean -d ticket_manager ARQUIVO.dump
sudo tar -xzf anexos_DATA.tar.gz -C /var/lib/ticket-manager
```

Guarde cópias dos backups **fora** do servidor.

## Atualizar o sistema

```bash
cd /opt/ticket-manager && sudo git pull
sudo /opt/ticket-manager/.venv/bin/pip install -r requirements.txt
sudo -u ticket TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py migrar
sudo systemctl restart ticket-manager
```

## HTTPS (recomendado se houver acesso de fora da rede)

Com um domínio apontando para o servidor:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chamados.suaempresa.com.br
```

Depois, em `config.ini`, defina `cookie_seguro = true` e reinicie o serviço.

## Problemas comuns

| Sintoma | Onde olhar |
|---|---|
| Página "502 Bad Gateway" | `sudo journalctl -u ticket-manager -n 50` (serviço parado ou erro no config.ini) |
| Erro de senha do banco | `url` em `[banco]`; caracteres especiais na senha precisam de codificação (`@` → `%40`) |
| Anexo não salva | permissão de `/var/lib/ticket-manager/anexos` (dono deve ser `ticket`) |
| Upload "arquivo grande demais" | `client_max_body_size` no Nginx e `anexo_max_mb` no config.ini |
