#!/bin/bash
# Copia para o NAS os backups (todo dia) e os logs (toda semana), confere o hash e registra.
#
#   copia-nas.sh backup   banco e anexos de /var/backups/ticket-manager → NAS; apaga do servidor
#                         só os arquivos cujo hash no NAS confere
#   copia-nas.sh logs     compacta os logs da última semana e envia ao NAS
#
# Configuração: /etc/ticket-manager/nas.conf (modelo em deploy/nas.conf.example).
# Registro: cada execução grava OK ou ERRO, com o hash, em /var/log/copia-nas.log.
# Agendar (como root, sudo crontab -e):
#   0 3 * * *  /bin/bash /opt/ticket-manager/deploy/copia-nas.sh backup
#   45 6 * * 0 /bin/bash /opt/ticket-manager/deploy/copia-nas.sh logs
set -uo pipefail

CONF=/etc/ticket-manager/nas.conf
REGISTRO=/var/log/copia-nas.log
ORIGEM_BACKUP=/var/backups/ticket-manager
MODO=${1:-}

registrar() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$REGISTRO"; }
falhar() { registrar "ERRO $MODO: $*"; exit 1; }

[[ $MODO == backup || $MODO == logs ]] || { echo "Uso: $0 backup|logs"; exit 2; }
[[ $EUID -eq 0 ]] || { echo "Rode como root (sudo)."; exit 2; }
umask 077

[[ -r $CONF ]] || falhar "arquivo de configuração $CONF não encontrado"
# shellcheck source=/dev/null
source "$CONF"
NOME_SERVIDOR=${NOME_SERVIDOR:-$(hostname -s)}
RETENCAO_BACKUP_DIAS=${RETENCAO_BACKUP_DIAS:-90}
RETENCAO_LOGS_DIAS=${RETENCAO_LOGS_DIAS:-365}
[[ -r ${NAS_CREDENCIAIS:-} ]] || falhar "arquivo de credenciais do NAS não encontrado (NAS_CREDENCIAIS)"

if [[ $MODO == backup ]]; then
    COMPARTILHAMENTO=${NAS_BACKUP:?defina NAS_BACKUP em $CONF}
    SUBPASTA="$NOME_SERVIDOR/backup"
    RETENCAO=$RETENCAO_BACKUP_DIAS
else
    COMPARTILHAMENTO=${NAS_LOGS:?defina NAS_LOGS em $CONF}
    SUBPASTA="$NOME_SERVIDOR/logs"
    RETENCAO=$RETENCAO_LOGS_DIAS
fi

# ─── monta o compartilhamento (desmonta ao sair, mesmo com erro) ────────────
PONTO=$(mktemp -d /mnt/copia-nas.XXXXXX)
TEMP=""
limpar() {
    umount "$PONTO" 2>/dev/null
    rmdir "$PONTO" 2>/dev/null
    [[ -n $TEMP ]] && rm -rf "$TEMP"
}
trap limpar EXIT

# cache=none: ao conferir o hash, o arquivo é lido de novo do NAS (não da memória do servidor)
mount -t cifs "$COMPARTILHAMENTO" "$PONTO" \
    -o "credentials=$NAS_CREDENCIAIS,vers=3.0,cache=none,uid=0,gid=0,file_mode=0600,dir_mode=0700" \
    || falhar "não foi possível montar $COMPARTILHAMENTO (NAS ligado? usuário e senha certos?)"
DESTINO="$PONTO/$SUBPASTA"
mkdir -p "$DESTINO" || falhar "não foi possível criar a pasta $SUBPASTA no NAS"

# Copia um arquivo, lê de volta do NAS e compara o SHA-256. Grava <arquivo>.sha256 ao lado.
# Usa um nome temporário: um arquivo pela metade nunca fica com o nome final.
copiar_conferir() {
    local arquivo=$1 nome hash_local hash_nas
    nome=$(basename "$arquivo")
    hash_local=$(sha256sum "$arquivo" | cut -d' ' -f1)
    if ! cp "$arquivo" "$DESTINO/$nome.parcial"; then
        registrar "ERRO $MODO: falha ao copiar $nome"
        rm -f "$DESTINO/$nome.parcial"
        return 1
    fi
    hash_nas=$(sha256sum "$DESTINO/$nome.parcial" | cut -d' ' -f1)
    if [[ $hash_local != "$hash_nas" ]]; then
        registrar "ERRO $MODO: hash diferente no NAS para $nome (local $hash_local, NAS $hash_nas)"
        rm -f "$DESTINO/$nome.parcial"
        return 1
    fi
    mv -f "$DESTINO/$nome.parcial" "$DESTINO/$nome"
    echo "$hash_local  $nome" > "$DESTINO/$nome.sha256"
    registrar "OK $MODO: $nome ($(du -h "$arquivo" | cut -f1)) sha256=$hash_local"
}

erros=0

if [[ $MODO == backup ]]; then
    # só arquivos prontos (sem mudança há 5 minutos), caso o backup.sh ainda esteja rodando
    mapfile -t arquivos < <(find "$ORIGEM_BACKUP" -maxdepth 1 -type f -mmin +5 \( -name 'banco_*' -o -name 'anexos_*' \) | sort)
    [[ ${#arquivos[@]} -gt 0 ]] || registrar "AVISO backup: nenhum arquivo novo em $ORIGEM_BACKUP"
    for f in "${arquivos[@]}"; do
        if copiar_conferir "$f"; then
            rm -f "$f"                       # só apaga do servidor o que está conferido no NAS
        else
            erros=$((erros + 1))
        fi
    done
else
    TEMP=$(mktemp -d)
    PACOTE="$TEMP/logs_${NOME_SERVIDOR}_$(date +%Y%m%d).tar.gz"
    mkdir -p "$TEMP/logs"
    # serviço (o nome pode ser ticketapp ou ticket-manager), Nginx e PostgreSQL da última semana
    journalctl --since "8 days ago" --no-pager -u ticketapp -u ticket-manager -u nginx -u postgresql \
        > "$TEMP/logs/journal.txt" 2>/dev/null
    for origem in /var/log/nginx /var/log/postgresql; do
        [[ -d $origem ]] && find "$origem" -maxdepth 1 -type f -mtime -8 -exec cp -p {} "$TEMP/logs/" \;
    done
    for f in /var/log/auth.log /var/log/auth.log.1 "$REGISTRO"; do
        [[ -f $f ]] && cp -p "$f" "$TEMP/logs/"
    done
    tar -czf "$PACOTE" -C "$TEMP" logs || falhar "não foi possível compactar os logs"
    copiar_conferir "$PACOTE" || erros=$((erros + 1))
fi

# ─── retenção no NAS (0 = guarda para sempre) ───────────────────────────────
if [[ $RETENCAO -gt 0 ]]; then
    find "$DESTINO" -maxdepth 1 -type f -mtime +"$RETENCAO" -delete
fi

if [[ $erros -gt 0 ]]; then
    registrar "ERRO $MODO: $erros arquivo(s) com falha; ficaram no servidor para a próxima tentativa"
    exit 1
fi
exit 0
