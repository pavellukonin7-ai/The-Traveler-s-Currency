#!/usr/bin/env bash
set -Eeuo pipefail

project_source="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="${1:-/root/currency_bot}"
service_name="${2:-currency-bot.service}"
backup_root="/root/currency-bot-backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backup_root/$stamp"

install -d -m 700 "$backup_dir"

if [[ -d "$target_dir" ]]; then
    tar -C "$target_dir" \
        --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache \
        -czf "$backup_dir/project.tar.gz" .
fi

if [[ -f "/etc/systemd/system/$service_name" ]]; then
    cp "/etc/systemd/system/$service_name" "$backup_dir/$service_name"
fi

install -d -m 755 "$target_dir"

if [[ ! -f "$target_dir/.env" && -f "$target_dir/config.py" ]]; then
    python3 - "$target_dir/config.py" "$target_dir/.env" <<'PY'
import ast
import shlex
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
wanted = {"TELEGRAM_BOT_TOKEN", "EXCHANGE_RATE_ACCESS_KEY", "DATABASE_PATH"}
values = {}
tree = ast.parse(source.read_text(encoding="utf-8"))
for node in tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if isinstance(target, ast.Name) and target.id in wanted:
        try:
            values[target.id] = str(ast.literal_eval(node.value))
        except (ValueError, TypeError):
            pass
lines = [f"{key}={shlex.quote(values.get(key, ''))}" for key in sorted(wanted)]
lines.append("LOG_LEVEL=INFO")
destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
destination.chmod(0o600)
PY
fi

for file_name in bot.py config.py country_currency.py current_api.py database.py exporter.py formatters.py keyboards.py requirements.txt README.md CHANGELOG.md VERSION .env.example .gitignore; do
    install -m 644 "$project_source/$file_name" "$target_dir/$file_name"
done

python3 -m venv "$target_dir/.venv"
"$target_dir/.venv/bin/python" -m pip install --upgrade pip
"$target_dir/.venv/bin/pip" install -r "$target_dir/requirements.txt"

if [[ ! -f "$target_dir/.env" ]]; then
    cp "$target_dir/.env.example" "$target_dir/.env"
    chmod 600 "$target_dir/.env"
    echo "Заполните $target_dir/.env и повторите запуск update.sh."
    exit 2
fi

cp "$project_source/deploy/currency-bot.service" "/etc/systemd/system/$service_name"
systemctl daemon-reload
systemctl enable "$service_name"
systemctl restart "$service_name"
systemctl --no-pager --full status "$service_name"

echo "Обновление завершено. Резервная копия: $backup_dir"

