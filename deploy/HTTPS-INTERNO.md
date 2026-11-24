# HTTPS na rede interna (ticket.internal)

Sem HTTPS, o navegador mostra **"Não seguro"** na barra de endereço. Como `ticket.internal` é um nome
só da rede interna, nenhuma autoridade pública (como o Let's Encrypt) emite certificado para ele. A
solução é uma **autoridade certificadora (CA) própria da empresa**, criada no OPNsense. Os passos são:

1. Criar a CA no OPNsense e, com ela, o certificado do `ticket.internal`.
2. Instalar o certificado e a chave no servidor e ligar o HTTPS no Nginx.
3. Instalar o **certificado da CA** (só ele, nunca a chave) em cada computador. A partir daí, o
   navegador confia em qualquer certificado que essa CA emitir.

Leva uns 20 minutos, mais a instalação nos computadores.

## 1. OPNsense: CA e certificado

### 1.1 Autoridade certificadora (uma vez só, vale 10 anos)

Em **System → Trust → Authorities**, clique em **+** e preencha:

| Campo | Valor |
|---|---|
| Method | Create an internal Certificate Authority |
| Description | CA interna da empresa |
| Key type / tamanho | RSA, 4096 |
| Digest | SHA256 |
| Lifetime (days) | 3650 |
| Common Name | CA interna da empresa (pode colocar o nome da empresa) |
| Country, State, City, Organization | da empresa |

Salve. Na lista, use o ícone de **download do certificado** (não o da chave) e salve como
**`ca-empresa.crt`**.

> A **chave** da CA fica só no OPNsense. Quem tiver essa chave consegue criar certificados em que todos
> os computadores confiam, então nunca a exporte nem a copie.

### 1.2 Certificado do ticket.internal

Em **System → Trust → Certificates**, clique em **+** e preencha:

| Campo | Valor |
|---|---|
| Method | Create an internal Certificate |
| Description | ticket.internal |
| Issuer | CA interna da empresa |
| Type | Server Certificate |
| Key type / tamanho | RSA, 2048 |
| Digest | SHA256 |
| Lifetime (days) | 825 (cerca de 2 anos e 3 meses: é o máximo que iPhone e Mac aceitam) |
| Common Name | ticket.internal |
| Alternative Names | DNS: `ticket.internal` · IP: o IP do servidor |

Salve. Na lista, baixe o **certificado** e a **chave** e renomeie para `ticket.internal.crt` e
`ticket.internal.key`.

## 2. Servidor Ubuntu

### 2.1 Copiar o certificado e a chave

No computador onde estão os arquivos, abra o PowerShell na pasta deles e copie para o servidor.
O `scp` já vem no Windows 10 e 11.

```powershell
scp ticket.internal.crt ticket.internal.key USUARIO@IP_DO_SERVIDOR:/tmp/
```

No servidor:

```bash
sudo mkdir -p /etc/ssl/ticket-manager
sudo mv /tmp/ticket.internal.crt /tmp/ticket.internal.key /etc/ssl/ticket-manager/
sudo chown root:root /etc/ssl/ticket-manager/*
sudo chmod 644 /etc/ssl/ticket-manager/ticket.internal.crt
sudo chmod 600 /etc/ssl/ticket-manager/ticket.internal.key
```

Depois de copiar, apague a chave do computador.

### 2.2 Nginx com HTTPS

```bash
cd /opt/ticket-manager && sudo -u ticketapp git pull
sudo cp /etc/nginx/sites-available/ticket-manager /etc/nginx/ticket-manager-http.bak
sudo cp /opt/ticket-manager/deploy/nginx-ticket-manager-https.conf /etc/nginx/sites-available/ticket-manager
sudo nginx -t && sudo systemctl reload nginx
```

O `nginx -t` deve mostrar "syntax is ok" e "test is successful". Se o firewall do Ubuntu estiver
ativo, libere a porta 443:

```bash
sudo ufw allow 'Nginx Full'
```

A porta 80 continua aberta, mas só redireciona para `https://ticket.internal`. Os links antigos e os
favoritos com `http://` continuam funcionando.

### 2.3 config.ini

```bash
sudo nano /etc/ticket-manager/config.ini
```

Em `[servidor]`:

```ini
cookie_seguro = true
atras_de_proxy = true
```

Em `[email]`, para os links dos avisos saírem com HTTPS:

```ini
url_site = https://ticket.internal
```

Depois reinicie o serviço:

```bash
sudo systemctl restart ticketapp
```

Com `cookie_seguro = true`, o login só funciona por HTTPS. Faça este passo junto com o 2.2.

### Voltar atrás, se precisar

```bash
sudo cp /etc/nginx/ticket-manager-http.bak /etc/nginx/sites-available/ticket-manager
sudo systemctl reload nginx
```

Depois volte `cookie_seguro = false` e `url_site = http://ticket.internal` no `config.ini` e
reinicie o serviço.

## 3. Computadores: instalar o certificado da CA

Coloque numa pasta pública, por exemplo `F:\publico\certificado`, estes dois arquivos:

- `ca-empresa.crt`, baixado no passo 1.1;
- `instalar-certificado.bat`, que está em `deploy/certificado/` neste repositório.

Cada computador roda o `.bat` com **dois cliques**. Ele funciona de dois jeitos:

| Como roda | Instala para | Observação |
|---|---|---|
| **Botão direito → Executar como administrador** (feito pela T.I) | Todos os usuários do computador | Recomendado. Não pergunta nada. |
| Dois cliques normais (feito pelo próprio usuário) | Só aquele usuário do Windows | O Windows mostra um "Aviso de Segurança": clicar em **Sim**. |

Depois feche e abra o navegador. O `https://ticket.internal` abre com o cadeado.

- **Chrome e Edge** usam os certificados do Windows. Não precisa de mais nada.
- **Firefox**: as versões atuais também usam. Se ainda avisar, abra `about:config` e ative
  `security.enterprise_roots.enabled`.
- **Celulares**: envie o `ca-empresa.crt` para o aparelho e instale.
  - Android: Configurações → Segurança → Criptografia e credenciais → Instalar certificado → Certificado de CA.
  - iPhone: abra o arquivo para instalar o perfil, depois vá em Ajustes → Geral → Sobre → Ajustes de
    Confiança de Certificado e ative a CA.

Para conferir num computador, rode `certmgr.msc` (usuário) ou `certlm.msc` (todos os usuários) e
procure a CA em **Autoridades de Certificação Raiz Confiáveis → Certificados**.

## Renovação

O certificado do `ticket.internal` vence em 825 dias. Cadastre uma **Tarefa da T.I** ("Renovar
certificado do ticket.internal") para um mês antes do vencimento. Para renovar, repita os passos 1.2 e
2.1 e rode `sudo systemctl reload nginx`. **Os computadores não precisam de nada**, porque a CA
continua a mesma, válida por 10 anos.

## Problemas comuns

| O que aparece | Causa e solução |
|---|---|
| "Sua conexão não é particular" / `NET::ERR_CERT_AUTHORITY_INVALID` | O computador ainda não tem o certificado da CA. Rode o `instalar-certificado.bat`. |
| `ERR_CERT_COMMON_NAME_INVALID` | Acessou por um nome que não está no certificado. Use `https://ticket.internal`, ou inclua o nome ou IP em "Alternative Names" e gere o certificado de novo. |
| Login volta sempre para a tela de entrada | `cookie_seguro = true`, mas o acesso foi por `http://`. Confira se o Nginx foi trocado (passo 2.2). |
| Links dos e-mails ainda com `http://` | Ajuste `url_site` no `config.ini` e reinicie o serviço. |
| `nginx -t` acusa "cannot load certificate" | Confira o nome e as permissões dos arquivos em `/etc/ssl/ticket-manager/`. |
