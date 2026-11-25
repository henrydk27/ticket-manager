#!/bin/bash
# Copia diaria do backup do Ticket Manager para o NAS (pasta cpd-backup)
# Mesmo modelo do copia-logs-nas.sh. Diferenca: depois de copiar, le o arquivo de volta do NAS,
# confere o hash e so entao APAGA o backup do servidor. Se algo falhar, o arquivo fica no servidor
# e vai na proxima execucao (o backup.sh continua apagando o que passar de 14 dias).
ORIGEM=/var/backups/ticket-manager

NAS_IP=IP_DO_NAS                 # AJUSTE: IP do NAS
COMPART=cpd-backup               # AJUSTE: pasta compartilhada dos backups
CRED=/root/.cred-nas-backup
RETENCAO_DIAS=90                 # backups mais antigos que isso sao apagados do NAS (0 = nunca; so com cifs)
HOST=$(hostname -s)
TMP=/tmp/copia-backup-$HOST
MNT=/mnt/nas-backup
log() { echo "$(date '+%F %T') $1"; }
trap 'mountpoint -q "$MNT" 2>/dev/null && umount "$MNT"; rm -rf "$TMP"' EXIT
umask 077

# 1) Backups prontos (sem mudanca ha 5 minutos) e o hash de cada um
mapfile -t ARQS < <(find "$ORIGEM" -maxdepth 1 -type f -mmin +5 \( -name 'banco_*' -o -name 'anexos_*' \) -printf '%f\n' | sort)
[ ${#ARQS[@]} -gt 0 ] || { log "AVISO: nenhum backup novo em $ORIGEM"; exit 0; }
rm -rf "$TMP"; mkdir -p "$TMP/conferir"
for A in "${ARQS[@]}"; do
    (cd "$ORIGEM" && sha256sum "$A") > "$TMP/$A.sha256" || { log "ERRO: falha ao calcular o hash de $A"; exit 1; }
done

ERROS=0
confirmado() {   # $1 = arquivo; apaga do servidor e registra OK
    rm -f "$ORIGEM/$1"
    log "OK: $1 copiado ($METODO), sha256=$(cut -d' ' -f1 "$TMP/$1.sha256")"
}
falhou() { log "ERRO: $1"; ERROS=$((ERROS + 1)); }

# 2) Envia para o NAS, confere e apaga do servidor (usa cifs-utils se existir; senao, smbclient)
if command -v mount.cifs >/dev/null 2>&1; then
    mkdir -p "$MNT"
    # cache=none: a conferencia le o arquivo do NAS, nao da memoria do servidor
    mount -t cifs "//$NAS_IP/$COMPART" "$MNT" -o credentials=$CRED,vers=3.0,cache=none 2>/dev/null \
      || mount -t cifs "//$NAS_IP/$COMPART" "$MNT" -o credentials=$CRED,vers=2.1,cache=none 2>/dev/null \
      || { log "ERRO: nao foi possivel montar o NAS"; exit 1; }
    METODO="cifs"
    mkdir -p "$MNT/$HOST"
    for A in "${ARQS[@]}"; do
        if ! cp "$ORIGEM/$A" "$TMP/$A.sha256" "$MNT/$HOST/"; then
            falhou "falha ao copiar $A para o NAS"; continue
        fi
        if (cd "$MNT/$HOST" && sha256sum -c --quiet "$A.sha256" >/dev/null 2>&1); then
            confirmado "$A"
        else
            falhou "hash de $A no NAS nao confere (mantido no servidor)"
        fi
    done
    [ "$RETENCAO_DIAS" -gt 0 ] && find "$MNT/$HOST" -maxdepth 1 -type f -mtime +"$RETENCAO_DIAS" -delete
elif command -v smbclient >/dev/null 2>&1; then
    PROTO=""
    for V in SMB3 SMB2; do
        smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $V -c "ls" >/dev/null 2>&1 && { PROTO=$V; break; }
    done
    [ -n "$PROTO" ] || { log "ERRO: nao foi possivel conectar ao NAS"; exit 1; }
    METODO="smbclient/$PROTO"
    smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO -c "mkdir $HOST" >/dev/null 2>&1
    for A in "${ARQS[@]}"; do
        smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO \
            -c "cd $HOST; lcd $ORIGEM; put $A; lcd $TMP; put $A.sha256" >/dev/null 2>&1
        # baixa de volta e confere o hash
        rm -f "$TMP/conferir/$A"
        smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO -c "cd $HOST; lcd $TMP/conferir; get $A" >/dev/null 2>&1
        if (cd "$TMP/conferir" && sha256sum -c --quiet "../$A.sha256" >/dev/null 2>&1); then
            confirmado "$A"
        else
            falhou "hash de $A no NAS nao confere (mantido no servidor)"
        fi
        rm -f "$TMP/conferir/$A"
    done
else
    log "ERRO: instale cifs-utils ou smbclient"; exit 1
fi

[ "$ERROS" -eq 0 ] || { log "ERRO: $ERROS arquivo(s) com falha; ficaram no servidor para a proxima execucao"; exit 1; }
