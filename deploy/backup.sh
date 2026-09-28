#!/bin/bash
# Backup diário do banco e dos anexos. Guarda os últimos 14 dias.
# Agendar (como root):  crontab -e  →  30 2 * * * /bin/bash /opt/ticket-manager/deploy/backup.sh
set -euo pipefail

DESTINO=/var/backups/ticket-manager
DATA=$(date +%Y%m%d_%H%M)

# Backups contêm dados dos usuários: só o root lê
umask 077
mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

sudo -u postgres pg_dump --format=custom ticket_manager > "$DESTINO/banco_$DATA.dump"
tar -czf "$DESTINO/anexos_$DATA.tar.gz" -C /var/lib/ticket-manager anexos

find "$DESTINO" -type f -mtime +14 -delete
