#!/bin/sh
# Снять бэкап Postgres и сразу проверить, что он разворачивается.
# Непроверенный бэкап — это не бэкап, а надежда.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="${BACKUP_DIR}/lms-${STAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Снимаю бэкап ${FILE}"
# формат custom: разворачивается выборочно и жмётся
pg_dump --format=custom --compress=6 --file="$FILE" "$PGDATABASE"

SIZE=$(wc -c < "$FILE")
if [ "$SIZE" -lt 1024 ]; then
    echo "ОШИБКА: бэкап подозрительно мал (${SIZE} байт)" >&2
    exit 1
fi

echo "[$(date -Iseconds)] Проверяю восстановление во временную базу"
VERIFY_DB="verify_${STAMP}"
createdb "$VERIFY_DB"

# ловушка: временная база убирается в любом случае
cleanup() {
    dropdb --if-exists "$VERIFY_DB" 2>/dev/null || true
}
trap cleanup EXIT

pg_restore --dbname="$VERIFY_DB" --no-owner --no-privileges "$FILE" >/dev/null 2>&1 || {
    echo "ОШИБКА: бэкап не разворачивается" >&2
    exit 1
}

# считаем таблицы: пустая схема означает, что дамп бесполезен
TABLES=$(psql -d "$VERIFY_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
if [ "$TABLES" -lt 10 ]; then
    echo "ОШИБКА: в восстановленной базе всего ${TABLES} таблиц" >&2
    exit 1
fi

STUDENTS=$(psql -d "$VERIFY_DB" -tAc "SELECT count(*) FROM students_student" 2>/dev/null || echo "н/д")

echo "[$(date -Iseconds)] Бэкап проверен: ${FILE}, таблиц ${TABLES}, учеников ${STUDENTS}, размер ${SIZE} байт"
echo "$STAMP OK tables=$TABLES students=$STUDENTS size=$SIZE" >> "${BACKUP_DIR}/verified.log"

# --- Загруженные файлы -----------------------------------------------------
# База без файлов — половина бэкапа: материалы олимпиадников лежат
# на диске, и без них восстановленная система будет ссылаться в пустоту.
FILES="${BACKUP_DIR}/files-${STAMP}.tar.gz"
if [ -d /app/media ] || [ -d /app/private ]; then
    echo "[$(date -Iseconds)] Складываю загруженные файлы в ${FILES}"
    tar -czf "$FILES" -C /app $( [ -d /app/media ] && echo media ) $( [ -d /app/private ] && echo private ) \
        2>/dev/null || echo "ПРЕДУПРЕЖДЕНИЕ: файлы сложить не удалось" >&2
    if [ -f "$FILES" ]; then
        # проверяем, что архив читается: битый tar молча ничего не восстановит
        tar -tzf "$FILES" >/dev/null 2>&1 || {
            echo "ОШИБКА: архив файлов не читается" >&2
            exit 1
        }
        echo "[$(date -Iseconds)] Архив файлов проверен: $(wc -c < "$FILES") байт"
    fi
else
    echo "[$(date -Iseconds)] Каталогов с файлами нет — архивировать нечего"
fi

echo "[$(date -Iseconds)] Удаляю бэкапы старше ${KEEP_DAYS} дней"
find "$BACKUP_DIR" -name 'lms-*.dump' -mtime "+${KEEP_DAYS}" -delete
find "$BACKUP_DIR" -name 'files-*.tar.gz' -mtime "+${KEEP_DAYS}" -delete

echo "[$(date -Iseconds)] Готово"
