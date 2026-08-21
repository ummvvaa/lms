#!/bin/sh
# Периодический запуск бэкапа. Отдельный контейнер, а не cron на хосте:
# так расписание уезжает вместе с контуром.
set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

echo "[$(date -Iseconds)] Служба бэкапов запущена, интервал ${INTERVAL} с"
# первый бэкап — сразу после старта, чтобы проблема вскрылась не через сутки
while true; do
    /scripts/backup.sh || echo "[$(date -Iseconds)] Бэкап завершился с ошибкой" >&2
    sleep "$INTERVAL"
done
