#!/bin/sh
# Развернуть бэкап в рабочую базу. Осознанно требует подтверждения:
# восстановление затирает текущие данные.
set -eu

FILE="${1:-}"
if [ -z "$FILE" ]; then
    echo "Использование: restore.sh /backups/lms-YYYYmmdd-HHMMSS.dump [--force]" >&2
    echo "Доступные бэкапы:" >&2
    ls -1t /backups/lms-*.dump 2>/dev/null | head -20 >&2
    exit 1
fi

if [ ! -f "$FILE" ]; then
    echo "ОШИБКА: файл $FILE не найден" >&2
    exit 1
fi

if [ "${2:-}" != "--force" ]; then
    echo "ВНИМАНИЕ: восстановление затрёт текущее содержимое базы ${PGDATABASE}."
    echo "Повторите с флагом --force, если это то, что нужно."
    exit 1
fi

echo "[$(date -Iseconds)] Восстанавливаю ${FILE} в ${PGDATABASE}"
pg_restore --dbname="$PGDATABASE" --clean --if-exists --no-owner --no-privileges "$FILE"
echo "[$(date -Iseconds)] База восстановлена"

# --- Загруженные файлы -----------------------------------------------------
# Рядом с дампом лежит архив файлов того же времени. Без него материалы
# олимпиадников и загруженные картинки останутся ссылками в пустоту.
STAMP=$(basename "$FILE" | sed -e 's/^lms-//' -e 's/\.dump$//')
FILES="$(dirname "$FILE")/files-${STAMP}.tar.gz"
if [ -f "$FILES" ]; then
    echo "[$(date -Iseconds)] Разворачиваю файлы из ${FILES}"
    tar -xzf "$FILES" -C /app
    echo "[$(date -Iseconds)] Файлы восстановлены"
else
    echo "ПРЕДУПРЕЖДЕНИЕ: архива файлов ${FILES} нет — восстановлена только база" >&2
fi

echo "[$(date -Iseconds)] Восстановление завершено"
