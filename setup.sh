#!/bin/bash
set -e
cd /opt/bybit-bot

if [ ! -f .env ]; then
  echo "File .env belum ada di /opt/bybit-bot. Buat dulu, lalu jalankan ulang: bash setup.sh"
  exit 1
fi

timedatectl set-timezone Asia/Jakarta
apt-get update
apt-get install -y python3-requests python3-dotenv

cp bybit-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable bybit-bot
systemctl restart bybit-bot
sleep 5
systemctl status bybit-bot --no-pager
journalctl -u bybit-bot -n 20 --no-pager
