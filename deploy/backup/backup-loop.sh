#!/bin/sh
# Ежедневный запуск бэкапа в заданный час. Отдельный контейнер, а не cron
# на хосте: так расписание уезжает вместе с контуром.
#
# Час задаётся BACKUP_HOUR (0–23, по местному времени контейнера — TZ
# из .env.prod). Первый бэкап — сразу после старта, чтобы проблема
# вскрылась сейчас, а не ночью.
set -eu

# доступ к базе — из тех же переменных, что у самого Postgres в env_file
export PGHOST="${PGHOST:-postgres}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-lms}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-lms}}"

HOUR="${BACKUP_HOUR:-3}"

echo "[$(date -Iseconds)] Служба бэкапов запущена, ежедневно в ${HOUR}:00 (${TZ:-UTC})"
/scripts/backup.sh || echo "[$(date -Iseconds)] Стартовый бэкап завершился с ошибкой" >&2

while true; do
    # секунд до следующего наступления часа HOUR
    now_h=$(date +%H | sed 's/^0//'); now_m=$(date +%M | sed 's/^0//'); now_s=$(date +%S | sed 's/^0//')
    now=$(( ${now_h:-0} * 3600 + ${now_m:-0} * 60 + ${now_s:-0} ))
    target=$(( HOUR * 3600 ))
    wait=$(( target - now ))
    [ "$wait" -le 0 ] && wait=$(( wait + 86400 ))
    echo "[$(date -Iseconds)] Следующий бэкап через ${wait} с"
    sleep "$wait"
    /scripts/backup.sh || echo "[$(date -Iseconds)] Бэкап завершился с ошибкой" >&2
done
