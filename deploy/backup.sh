#!/usr/bin/env bash
# 毎日のバックアップ：SQLite を安全にコピーして、暗号化して S3 へ（設計書 4-1）
# cron 例（root）: 15 3 * * * /opt/mamorinet/deploy/backup.sh >> /var/log/mamorinet-backup.log 2>&1
# EC2 には LabInstanceProfile（S3 への権限）をつけておく
set -euo pipefail
DB=${MAMORI_DB_PATH:-/var/lib/mamorinet/mamorinet.sqlite3}
BUCKET=${MAMORI_BACKUP_BUCKET:?MAMORI_BACKUP_BUCKET を設定してください（例 s3://mamorinet-backup-xxxx）}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
STAMP=$(TZ=Asia/Tokyo date +%Y%m%d-%H%M)
sqlite3 "$DB" ".backup '$TMP/mamorinet.sqlite3'"
gzip "$TMP/mamorinet.sqlite3"
aws s3 cp "$TMP/mamorinet.sqlite3.gz" "$BUCKET/mamorinet-$STAMP.sqlite3.gz" --sse AES256
echo "$(date -Is) backup ok: $BUCKET/mamorinet-$STAMP.sqlite3.gz"
