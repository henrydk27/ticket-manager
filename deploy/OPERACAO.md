# Operação do dia a dia

Como o sistema funciona depois de instalado e o que fazer em cada situação.
A instalação em si está em [INSTALACAO-UBUNTU.md](INSTALACAO-UBUNTU.md).

## Como funciona

```
Navegador  →  Nginx  →  Ticket Manager (Gunicorn)  →  PostgreSQL
                               ↓
                     /var/lib/ticket-manager/anexos
```

- **Nginx** recebe os acessos em `http://IP-DO-SERVIDOR` e repassa ao sistema.
- **Ticket Manager** roda como serviço (`ticket-manager`): liga sozinho quando o servidor
  reinicia e se reinicia sozinho se travar. Não precisa de ninguém logado no servidor.
- **PostgreSQL** guarda contas, chamados e comentários. Os **anexos** ficam em disco.
- **Backup** automático todo dia às 2h30, guardando 14 dias.

Os usuários não instalam nada: acessam pelo navegador (computador ou celular).

## Tarefas do administrador (pelo navegador)

| Situação | O que fazer |
|---|---|
| Pessoa nova | Ela mesma cria a conta em **Crie sua conta** na tela de login |
| Alguém vai atender chamados do setor | **Usuários** → confira o **Setor** → marque **Atende chamados** → **Salvar** |
| Alguém deixou de atender | Desmarque **Atende chamados**; os chamados em aberto com ela ficam sem responsável |
| Mudou de setor | **Usuários** → troque o **Setor** → **Salvar** (a pessoa não consegue mudar sozinha) |
| Esqueceu a senha | **Usuários** → **Redefinir senha** → passe a senha temporária à pessoa; no próximo acesso ela cria uma nova |
| Saiu da empresa | **Usuários** → **Desativar** (o acesso é cortado na hora; os chamados dela continuam no histórico) |
| Outro administrador | **Usuários** → perfil **Administrador** → **Salvar** (vê todos os chamados; o sistema sempre mantém pelo menos um) |
| Apagar um chamado | Só o administrador: abra o chamado → **Apagar chamado** (permanente) |

Um setor só aparece na tela de novo chamado quando tem pelo menos uma pessoa marcada como
**Atende chamados**.

### Quem vê o quê

- **Usuário:** só os chamados que ele mesmo abriu.
- **Quem atende chamados:** os chamados do seu setor, mais os que ele abriu para outros setores.
- **Administrador:** todos.

Para impedir que qualquer pessoa crie conta, defina `cadastro_aberto = false` no
`config.ini` (veja [Mudar a configuração](#mudar-a-configuração)).

## Comandos úteis no servidor

| Para | Comando |
|---|---|
| Ver se está rodando | `sudo systemctl status ticket-manager --no-pager` |
| Reiniciar | `sudo systemctl restart ticket-manager` |
| Ver erros recentes | `sudo journalctl -u ticket-manager -n 50 --no-pager` |
| Acompanhar em tempo real | `sudo journalctl -u ticket-manager -f` (Ctrl+C para sair) |
| Ver o IP do servidor | `hostname -I` |
| Espaço em disco | `df -h /` |
| Tamanho dos anexos | `sudo du -sh /var/lib/ticket-manager/anexos` |

## Atualizar o sistema

Quando houver alteração no código (enviada ao GitHub com `git push`):

```bash
cd /opt/ticket-manager
sudo git pull
sudo .venv/bin/pip install -r requirements.txt
sudo -u ticketapp TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py migrar
sudo systemctl restart ticket-manager
```

Os dados não se perdem: `migrar` só ajusta a estrutura do banco quando necessário.
Se mudou algum arquivo de `deploy/` (serviço ou Nginx), o aviso vem junto com a atualização.

## Mudar a configuração

```bash
sudo nano /etc/ticket-manager/config.ini
sudo systemctl restart ticket-manager
```

## Backup

- **Onde:** `/var/backups/ticket-manager` (só o root lê).
- **Arquivos:** `banco_DATA.dump` (banco) e `anexos_DATA.tar.gz` (anexos), um par por dia.
- **Conferir:** `sudo ls -lh /var/backups/ticket-manager` — deve haver arquivos de hoje (ou de ontem, antes das 2h30).
- **Rodar agora:** `sudo bash /opt/ticket-manager/deploy/backup.sh`

### Copiar para fora do servidor

Os backups ficam no mesmo disco do servidor; copie-os regularmente para outro lugar.
Para levar o mais recente para o seu computador (ex.: com WinSCP ou `scp`):

```bash
sudo bash -c 'cd /var/backups/ticket-manager && cp "$(ls -t banco_* | head -1)" "$(ls -t anexos_* | head -1)" "$1"' _ "$HOME"
sudo chown $USER ~/banco_* ~/anexos_*
```

Depois de copiar, apague do seu home: `rm ~/banco_* ~/anexos_*`.

### Restaurar um backup

Isso **substitui** os dados atuais pelos do backup.

```bash
sudo systemctl stop ticket-manager

# banco (troque pelo nome do arquivo)
sudo bash -c "sudo -u postgres pg_restore --clean --if-exists -d ticket_manager \
    < /var/backups/ticket-manager/banco_AAAAMMDD_HHMM.dump"

# anexos
sudo tar -xzf /var/backups/ticket-manager/anexos_AAAAMMDD_HHMM.tar.gz -C /var/lib/ticket-manager
sudo chown -R ticketapp:ticketapp /var/lib/ticket-manager

sudo systemctl start ticket-manager
```

## Se algo der errado

| Sintoma | O que verificar |
|---|---|
| Página não abre | O servidor está ligado? `sudo systemctl status nginx ticket-manager --no-pager` |
| `502 Bad Gateway` | Serviço parado ou com erro: veja os erros com `journalctl` (tabela acima) |
| Ninguém consegue entrar como administrador | `sudo -u ticketapp TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py tornar-admin LOGIN` (dentro de `/opt/ticket-manager`) |
| Disco cheio | `df -h /`; anexos antigos e backups ocupam espaço |
