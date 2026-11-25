#!/bin/bash
# Copia semanal de logs para o NAS (pasta cpd-log)
# AJUSTE AQUI: arquivos e pastas de log deste servidor (separados por espaco)
# Ticket Manager: servidor web (Nginx) + banco PostgreSQL
PASTAS="/var/log/auth.log* /var/log/nginx /var/log/postgresql"

NAS_IP=IP_DO_NAS                 # AJUSTE: IP do NAS (ver IT - Copia semanal de logs para o NAS)
COMPART=cpd-log
CRED=/root/.cred-nas-logs
HOST=$(hostname -s)
DATA=$(date +%Y-%m-%d)
ARQ="logs-$HOST-$DATA.tar.gz"
TMP=/tmp/copia-logs-$HOST
MNT=/mnt/nas-logs
log() { echo "$(date '+%F %T') $1"; }
trap 'mountpoint -q "$MNT" 2>/dev/null && umount "$MNT"; rm -rf "$TMP"' EXIT

# 1) Junta os logs, compacta e calcula o hash
rm -rf "$TMP"; mkdir -p "$TMP/logs"
for P in $PASTAS; do
    [ -e "$P" ] && cp -a "$P" "$TMP/logs/" 2>/dev/null
done
journalctl --since "8 days ago" --no-pager > "$TMP/logs/journal-$HOST.log" 2>/dev/null
tar -czf "$TMP/$ARQ" -C "$TMP/logs" . || { log "ERRO: falha ao compactar os logs"; exit 1; }
HASH=$(sha256sum "$TMP/$ARQ" | cut -d' ' -f1)
echo "$HASH  $ARQ" > "$TMP/$ARQ.sha256"

# 2) Envia para o NAS (usa cifs-utils se existir; senao, smbclient)
if command -v mount.cifs >/dev/null 2>&1; then
    mkdir -p "$MNT"
    mount -t cifs "//$NAS_IP/$COMPART" "$MNT" -o credentials=$CRED,vers=3.0 2>/dev/null \
      || mount -t cifs "//$NAS_IP/$COMPART" "$MNT" -o credentials=$CRED,vers=2.1 2>/dev/null \
      || { log "ERRO: nao foi possivel montar o NAS"; exit 1; }
    mkdir -p "$MNT/$HOST"
    cp "$TMP/$ARQ" "$TMP/$ARQ.sha256" "$MNT/$HOST/" || { log "ERRO: falha ao copiar para o NAS"; exit 1; }
    [ -f "$MNT/$HOST/$ARQ" ] || { log "ERRO: arquivo nao encontrado no NAS"; exit 1; }
    METODO="cifs"
elif command -v smbclient >/dev/null 2>&1; then
    PROTO=""
    for V in SMB3 SMB2; do
        smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $V -c "ls" >/dev/null 2>&1 && { PROTO=$V; break; }
    done
    [ -n "$PROTO" ] || { log "ERRO: nao foi possivel conectar ao NAS"; exit 1; }
    smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO -c "mkdir $HOST" >/dev/null 2>&1
    smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO -c "cd $HOST; lcd $TMP; put $ARQ; put $ARQ.sha256" >/dev/null 2>&1
    smbclient "//$NAS_IP/$COMPART" -A "$CRED" -m $PROTO -c "cd $HOST; ls $ARQ" 2>/dev/null | grep -q "$ARQ" \
      || { log "ERRO: arquivo nao encontrado no NAS"; exit 1; }
    METODO="smbclient/$PROTO"
else
    log "ERRO: instale cifs-utils ou smbclient"; exit 1
fi

log "OK: $ARQ copiado ($METODO), sha256=$HASH"
