#!/usr/bin/env bash

set -e

echo "[Telegram Family Assistant] Starting version ${TELEGRAM_FAMILY_ASSISTANT_VERSION:-unknown}"
exec python3 -m app.main
