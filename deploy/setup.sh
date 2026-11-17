#!/usr/bin/env bash
# Ubuntu Server 26.04 LTS（AWS Academy の EC2）に まもりネット を設置する
#   sudo DOMAIN=203-0-113-10.sslip.io EMAIL=you@example.com bash deploy/setup.sh
# DOMAIN を省くと、いまのパブリックIPから sslip.io の名前を作る（Learner Lab は再起動でIPが変わる → 再実行する）
set -euo pipefail
APP_DIR=/opt/mamorinet
SRC_DIR=$(cd "$(dirname "$0")/.." && pwd)

if [ -z "${DOMAIN:-}" ]; then
  TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
  DOMAIN="${IP//./-}.sslip.io"
fi
echo "DOMAIN=$DOMAIN"

apt-get update
apt-get install -y python3 python3-venv nginx certbot python3-certbot-nginx sqlite3 rsync fonts-noto-cjk

id mamorinet >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin mamorinet
mkdir -p "$APP_DIR" /var/lib/mamorinet
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  rsync -a --delete --exclude .git --exclude .venv --exclude .env --exclude '*.sqlite3' "$SRC_DIR/" "$APP_DIR/"
fi
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "⚠ $APP_DIR/.env を編集して LINE の鍵を入れてください"
fi
sed -i "s|^MAMORI_PUBLIC_URL=.*|MAMORI_PUBLIC_URL=https://$DOMAIN|" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
chown -R mamorinet:mamorinet "$APP_DIR/.env" /var/lib/mamorinet

sed "s/DOMAIN/$DOMAIN/" "$APP_DIR/deploy/nginx-mamorinet.conf" > /etc/nginx/sites-available/mamorinet
ln -sf /etc/nginx/sites-available/mamorinet /etc/nginx/sites-enabled/mamorinet
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

cp "$APP_DIR/deploy/mamorinet.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mamorinet

# 正式な証明書（LINE の Webhook に必要）
if [ -n "${EMAIL:-}" ]; then MAIL_OPT=(-m "$EMAIL"); else MAIL_OPT=(--register-unsafely-without-email); fi
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos "${MAIL_OPT[@]}" --redirect

echo
echo "✓ 設置完了: https://$DOMAIN/"
echo "  LINE Developers の Webhook URL に https://$DOMAIN/callback を設定し、「検証」を押してください"
