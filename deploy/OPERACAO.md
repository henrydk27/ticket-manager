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
- **PostgreSQL** guarda contas, chamados, comentários e o inventário. Os **anexos** ficam em disco.
- **Backup** automático todo dia às 2h30, guardando 14 dias.

Os usuários não instalam nada: acessam pelo navegador (computador ou celular). No canto da
tela, um botão alterna entre modo claro e escuro e outro (o círculo colorido) escolhe a cor do
sistema entre 7 opções. Cada navegador lembra a escolha da pessoa.

## Tarefas do administrador (pelo navegador)

| Situação | O que fazer |
|---|---|
| Pessoa nova | Ela mesma cria a conta em **Crie sua conta** na tela de login |
| Alguém vai atender chamados do setor | **Usuários** → confira o **Setor** → marque **Atende chamados** → **Salvar alterações** |
| Alguém deixou de atender | Desmarque **Atende chamados** → **Salvar alterações**; os chamados em aberto com ela ficam sem responsável |
| Mudou de setor | **Usuários** → troque o **Setor** → **Salvar alterações** (a pessoa não consegue mudar sozinha) |
| Esqueceu a senha | **Usuários** → **Redefinir senha** → passe a senha temporária à pessoa; no próximo acesso ela cria uma nova |
| Saiu da empresa | **Usuários** → **Desativar** (o acesso é cortado na hora; os chamados dela continuam no histórico) |
| Outro administrador | **Usuários** → perfil **Administrador** → **Salvar alterações** (vê todos os chamados; o sistema sempre mantém pelo menos um) |
| Apagar um chamado | Só o administrador: abra o chamado → **Apagar chamado** (permanente) |

Na tela **Usuários**, dá para mexer em várias linhas e salvar tudo de uma vez no botão
**Salvar alterações**, no rodapé. As linhas alteradas ficam destacadas, e o navegador avisa se
você tentar sair sem salvar. Se alguma linha tiver problema, nada é gravado.

Um setor só aparece na tela de novo chamado quando tem pelo menos uma pessoa marcada como
**Atende chamados**.

### Quem vê o quê

| | Chamados | Painel e relatório | Inventário | Usuários |
|---|---|---|---|---|
| **Usuário** | só os que ele abriu | — | — | — |
| **Quem atende chamados** | os do seu setor + os que ele abriu | do seu setor | — | — |
| **Administrador** | todos | todos os setores (com filtro) | sim | sim |

Para impedir que qualquer pessoa crie conta, defina `cadastro_aberto = false` no
`config.ini` (veja [Mudar a configuração](#mudar-a-configuração)).

## Inventário de TI

Menu **Inventário**, visível só para **administradores**.

| Situação | O que fazer |
|---|---|
| Cadastrar um equipamento | **+ Novo equipamento** → informe o nº de patrimônio que já está na etiqueta, o tipo e o que souber |
| Entregar a alguém | Abra o equipamento → escolha o **Usuário** (o setor dele é preenchido) → **Salvar alterações** |
| Deixar num setor, sem pessoa | Escolha só o **Setor** (ex.: impressora do Fiscal) |
| Voltou para a T.I | **Usuário** = Ninguém, **Setor** = Nenhum, **Situação** = Em estoque |
| Foi para conserto | **Situação** = Em manutenção |
| Não serve mais | **Situação** = Descartado (sai da lista, mas continua em "Todas as situações" com o histórico) |
| Planilha do inventário | **Exportar Excel** baixa a lista com os filtros aplicados |

Cada cadastro, troca de usuário, setor ou situação e edição fica no **Histórico** do equipamento,
com data e quem fez. Só o administrador pode apagar um equipamento de vez (prefira "Descartado").

## Painel e relatório

- **Painel:** números do setor (ou de todos, para o admin, com filtro de setor) nos últimos 30 dias,
  90 dias ou 12 meses: em aberto, sem responsável, abertos e encerrados no período e o **tempo
  médio até encerrar** (ex.: "3 h 20 min", "2 d 4 h"). Os gráficos levam à lista já filtrada.
- **Relatório:** chamados abertos num período, em **Excel** ou **PDF**.

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

Os dados não se perdem: `migrar` só ajusta a estrutura do banco quando necessário, e pode ser
rodado sempre, mesmo quando não há mudança no banco.

- Se a atualização trouxer uma opção nova de configuração, ela aparece no `config.example.ini`;
  copie para o `/etc/ticket-manager/config.ini` só se quiser usar (sem ela vale o padrão).
- Se mudou algum arquivo de `deploy/` (serviço ou Nginx), o aviso vem junto com a atualização.
- Os navegadores pegam o visual novo sozinhos (não precisa de Ctrl+F5).

## Mudar a configuração

```bash
sudo nano /etc/ticket-manager/config.ini
sudo systemctl restart ticket-manager
```

| Seção | Opção | Para que serve |
|---|---|---|
| `[banco]` | `url` | endereço e senha do PostgreSQL |
| `[servidor]` | `secret_key` | chave que protege as sessões (não compartilhe; trocar desconecta todo mundo) |
| | `anexos_pasta`, `anexo_max_mb` | onde ficam os anexos e o tamanho máximo de cada um |
| | `sessao_horas` | depois de quantas horas a pessoa precisa entrar de novo |
| | `cadastro_aberto` | `false` impede que novas pessoas criem conta sozinhas |
| | `atras_de_proxy`, `cookie_seguro` | `true` com Nginx na frente / com HTTPS |
| `[email]` | ver [Avisos por e-mail](#avisos-por-e-mail) | servidor SMTP dos avisos |

## Avisos por e-mail

O sistema manda e-mail quando:

| Acontece | Quem recebe |
|---|---|
| Chamado aberto | o funcionário escolhido |
| Chamado encaminhado | o novo responsável |
| Comentário | quem abriu e o responsável |
| Mudança de status | quem abriu |
| Chamado encerrado | quem abriu (com link para avaliar) |

Ninguém recebe aviso da própria ação, e contas desativadas não recebem nada.
O e-mail é obrigatório no cadastro; quem tinha conta sem e-mail é levado a preencher no próximo acesso.

### Configurar

1. Crie (ou peça ao responsável pelo e-mail da empresa) uma conta só para o sistema,
   por exemplo `chamados@suaempresa.com.br`, e anote a senha.
2. Copie a seção `[email]` do `config.example.ini` para o `config.ini` do servidor, se ainda não
   estiver lá, e preencha:

   ```bash
   sudo nano /etc/ticket-manager/config.ini
   ```

   ```ini
   [email]
   host = smtp.office365.com          ; servidor SMTP do seu provedor (veja a tabela abaixo)
   porta = 587
   seguranca = starttls               ; starttls, ssl ou nenhuma
   usuario = chamados@suaempresa.com.br
   senha = SENHA_DA_CONTA
   remetente = chamados@suaempresa.com.br
   nome = Ticket Manager
   url_site = http://IP-OU-NOME-DO-SERVIDOR
   ```

3. Teste e reinicie:

   ```bash
   cd /opt/ticket-manager
   sudo -u ticketapp TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py testar-email seu@email.com.br
   sudo systemctl restart ticket-manager
   ```

### Servidor de e-mail interno (da própria empresa)

Pergunte ao responsável pelo servidor de e-mail:

1. **Qual o endereço** do servidor (ex.: `mail.suaempresa.local` ou um IP).
2. **Se aceita envio sem senha** vindo do servidor do Ticket Manager (*relay* interno) ou se precisa de usuário e senha.
3. **Se o certificado é próprio** (autoassinado ou de uma autoridade interna da empresa).

Para descobrir sozinho quais portas estão abertas, rode no servidor do Ticket Manager
(troque `mail.suaempresa.local` pelo endereço do servidor de e-mail):

```bash
for p in 25 587 465; do nc -zv -w 3 mail.suaempresa.local $p; done
```

Configurações mais comuns num servidor interno:

```ini
; Envio sem senha pela rede interna (relay)
host = mail.suaempresa.local
porta = 25
seguranca = nenhuma
usuario =
senha =

; Envio com senha
host = mail.suaempresa.local
porta = 587
seguranca = starttls
usuario = chamados@suaempresa.com.br
senha = SENHA_DA_CONTA
```

Se o `testar-email` der **`CERTIFICATE_VERIFY_FAILED`**, o servidor usa certificado próprio.
O jeito seguro é salvar o certificado dele e informar em `ca_arquivo`:

```bash
# porta 587 (starttls); para a porta 465 (ssl), tire o "-starttls smtp" e troque a porta
openssl s_client -starttls smtp -connect mail.suaempresa.local:587 -showcerts </dev/null 2>/dev/null \
  | sudo sh -c 'sed -n "/BEGIN CERTIFICATE/,/END CERTIFICATE/p" > /etc/ticket-manager/certificado-email.crt'
sudo chmod 644 /etc/ticket-manager/certificado-email.crt
```

```ini
ca_arquivo = /etc/ticket-manager/certificado-email.crt
```

Se a empresa tiver uma autoridade certificadora própria, prefira o certificado dela (peça ao TI) ao
salvo pelo comando acima. Em último caso, `verificar_certificado = false` aceita qualquer
certificado; funciona, mas perde a proteção contra alguém se passar pelo servidor de e-mail.

O `host` precisa ser o **mesmo nome que está no certificado**. Se o certificado é de
`mail.suaempresa.local`, use esse nome, não o IP. Se o nome não resolve no servidor do Ticket
Manager, acrescente uma linha em `/etc/hosts`: `192.168.0.10  mail.suaempresa.local`.

### Provedores externos

| Provedor | host | porta | seguranca |
|---|---|---|---|
| Microsoft 365 / Outlook | `smtp.office365.com` | 587 | `starttls` |
| Google Workspace / Gmail | `smtp.gmail.com` | 587 | `starttls` (senha de app) |
| Locaweb | `email-ssl.com.br` | 465 | `ssl` |
| HostGator / cPanel | `mail.seudominio.com.br` | 465 | `ssl` |

Se o `testar-email` falhar:

| Mensagem | O que fazer |
|---|---|
| `SMTPAuthenticationError` | Usuário ou senha errados. No Microsoft 365, o administrador precisa liberar "SMTP autenticado" para a conta; no Google, use uma "senha de app". |
| `ConnectionRefusedError` / `timed out` | `host` ou `porta` errados, ou o provedor/firewall bloqueia a saída nessa porta. |
| `SSL` / `WRONG_VERSION_NUMBER` | Troque `seguranca`: porta 465 usa `ssl`, porta 587 usa `starttls`, porta 25 geralmente `nenhuma`. |
| `CERTIFICATE_VERIFY_FAILED` | Certificado próprio do servidor: veja "Servidor de e-mail interno" acima (`ca_arquivo`). |
| `hostname mismatch` / `doesn't match` | O `host` não é o nome que está no certificado: use o nome do certificado (e `/etc/hosts`, se preciso). |
| `SMTPRecipientsRefused` / `Relay access denied` | O servidor não aceita envio sem senha deste computador: use usuário e senha, ou peça ao TI para liberar o IP do servidor do Ticket Manager. |
| `STARTTLS extension not supported` | O servidor não oferece criptografia nessa porta: use `seguranca = nenhuma` (só dentro da rede interna). |
| `SMTPSenderRefused` | O `remetente` precisa ser a mesma conta do `usuario` (ou uma que ela possa usar). |

Se um aviso não chegar depois de configurado, o motivo aparece no log:
`sudo journalctl -u ticket-manager -n 50 --no-pager | grep -i e-mail`.

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
| Visual antigo ou botão que não responde depois de atualizar | Recarregue com **Ctrl+F5** (só pode acontecer com quem abriu o sistema antes da atualização que passou a versionar os arquivos) |
| Menu **Inventário** não aparece | Só administradores veem o inventário: em **Usuários**, mude o perfil da pessoa para **Administrador** |
| `502 Bad Gateway` | Serviço parado ou com erro: veja os erros com `journalctl` (tabela acima) |
| Ninguém consegue entrar como administrador | `sudo -u ticketapp TICKET_MANAGER_CONFIG=/etc/ticket-manager/config.ini .venv/bin/python manage.py tornar-admin LOGIN` (dentro de `/opt/ticket-manager`) |
| Disco cheio | `df -h /`; anexos antigos e backups ocupam espaço |
