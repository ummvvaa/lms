#!/bin/sh
# Выкат боевого контура в правильном порядке: собрать без кеша → проверить
# настройки → мигрировать → собрать статику → поднять.
#
# Скрипт, а не список команд в инструкции: список можно выполнить не в том
# порядке. Сборка всегда --no-cache: в фазе 55 выяснилось, что кеш слоёв
# держал пакеты, удалённые из requirements тремя фазами раньше, и в бой
# уехало бы не то, что описано.
#
# Первый запуск и обновление версии — одна и та же команда.
set -eu

cd "$(dirname "$0")"
COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env.prod ]; then
    echo "ОШИБКА: нет deploy/.env.prod. Скопируйте .env.prod.example и заполните (docs/DEPLOY.md)" >&2
    exit 1
fi

echo "==> 1/5 Сборка образов без кеша"
$COMPOSE build --no-cache --pull

echo "==> 2/5 База и Redis"
$COMPOSE up -d postgres redis
$COMPOSE run --rm --no-deps --entrypoint "" backend python - <<'PY'
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

echo "==> 3/5 Проверка боевых настроек"
# check --deploy падает на слабом ключе, пустых хостах и выключенных
# защитах — лучше здесь, чем узнать об этом из браузера
$COMPOSE run --rm --no-deps --entrypoint "" backend python manage.py check --deploy

echo "==> 4/5 Миграции и статика"
$COMPOSE run --rm --no-deps --entrypoint "" backend python manage.py migrate --noinput
$COMPOSE run --rm --no-deps --entrypoint "" backend python manage.py collectstatic --noinput

echo "==> 5/5 Подъём контура"
$COMPOSE up -d --remove-orphans

echo
$COMPOSE ps
echo
echo "Готово. Проверьте: curl -fsS https://<домен>/readyz"
