#!/bin/sh
# Ждём базу, накатываем миграции, запускаем то, что попросили.
set -e

echo "Ожидаю Postgres на ${POSTGRES_HOST}:${POSTGRES_PORT}..."
python - <<'PY'
import os, socket, time
host, port = os.environ.get("POSTGRES_HOST", "postgres"), int(os.environ.get("POSTGRES_PORT", 5432))
for _ in range(60):
    try:
        socket.create_connection((host, port), timeout=2).close()
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("Postgres не поднялся за 60 секунд")
PY

python manage.py migrate --noinput
exec "$@"
