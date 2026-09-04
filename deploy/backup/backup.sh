#!/bin/sh
# Снять бэкап Postgres, проверить, что он разворачивается, сложить файлы,
# выгрузить в объектное хранилище и подчистить старое.
# Непроверенный бэкап — это не бэкап, а надежда.
#
# Хранение: 7 ежедневных и 4 еженедельных. Еженедельный — это копия
# ежедневного, снятого в BACKUP_WEEKLY_DAY (по умолчанию воскресенье),
# в подкаталоге weekly/. Так же и в хранилище.
#
# Скрипт не знает, в каком облаке живёт: адрес, регион, бакет и ключи
# приходят переменными BACKUP_REMOTE_*. Пусто — бэкап остаётся локальным,
# и об этом громко сказано в логе.
set -eu

# доступ к базе — из тех же переменных, что у самого Postgres в env_file
export PGHOST="${PGHOST:-postgres}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-lms}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-lms}}"

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"
WEEKLY_DAY="${BACKUP_WEEKLY_DAY:-7}"   # день недели по ISO: 1 — понедельник, 7 — воскресенье
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="${BACKUP_DIR}/lms-${STAMP}.dump"

mkdir -p "$BACKUP_DIR" "$BACKUP_DIR/weekly"

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
# База без файлов — половина бэкапа: материалы олимпиадников и документы
# портфолио лежат на диске, и без них восстановленная система будет
# ссылаться в пустоту.
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

# --- Еженедельная копия ----------------------------------------------------
if [ "$(date +%u)" = "$WEEKLY_DAY" ]; then
    cp "$FILE" "$BACKUP_DIR/weekly/"
    [ -f "$FILES" ] && cp "$FILES" "$BACKUP_DIR/weekly/"
    echo "[$(date -Iseconds)] Еженедельная копия отложена в weekly/"
fi

# --- Выгрузка в объектное хранилище ---------------------------------------
# rclone настраивается переменными окружения, файла конфигурации нет:
# всё, что отличает одно облако от другого, — четыре строки в .env.prod
if [ -n "${BACKUP_REMOTE_BUCKET:-}" ]; then
    export RCLONE_CONFIG_STORE_TYPE=s3
    export RCLONE_CONFIG_STORE_PROVIDER="${BACKUP_REMOTE_PROVIDER:-Other}"
    export RCLONE_CONFIG_STORE_ENDPOINT="${BACKUP_REMOTE_ENDPOINT:-}"
    export RCLONE_CONFIG_STORE_REGION="${BACKUP_REMOTE_REGION:-}"
    export RCLONE_CONFIG_STORE_ACCESS_KEY_ID="${BACKUP_REMOTE_ACCESS_KEY:-}"
    export RCLONE_CONFIG_STORE_SECRET_ACCESS_KEY="${BACKUP_REMOTE_SECRET_KEY:-}"
    REMOTE="store:${BACKUP_REMOTE_BUCKET}/${BACKUP_REMOTE_PREFIX:-lms}"

    echo "[$(date -Iseconds)] Выгружаю в хранилище ${REMOTE}"
    rclone copy "$FILE" "$REMOTE/daily/" --s3-no-check-bucket
    [ -f "$FILES" ] && rclone copy "$FILES" "$REMOTE/daily/" --s3-no-check-bucket
    if [ "$(date +%u)" = "$WEEKLY_DAY" ]; then
        rclone copy "$FILE" "$REMOTE/weekly/" --s3-no-check-bucket
        [ -f "$FILES" ] && rclone copy "$FILES" "$REMOTE/weekly/" --s3-no-check-bucket
    fi
    # проверяем, что файл действительно лежит там и того же размера
    UPLOADED=$(rclone size "$REMOTE/daily/$(basename "$FILE")" --json 2>/dev/null | sed -n 's/.*"bytes":\([0-9]*\).*/\1/p')
    if [ "${UPLOADED:-0}" != "$SIZE" ]; then
        echo "ОШИБКА: в хранилище файл другого размера (${UPLOADED:-нет} против ${SIZE})" >&2
        exit 1
    fi
    echo "[$(date -Iseconds)] Выгрузка проверена: ${UPLOADED} байт в хранилище"

    echo "[$(date -Iseconds)] Чищу хранилище: ежедневные старше ${KEEP_DAILY} дн., еженедельные старше $((KEEP_WEEKLY * 7)) дн."
    rclone delete "$REMOTE/daily/" --min-age "${KEEP_DAILY}d" || true
    rclone delete "$REMOTE/weekly/" --min-age "$((KEEP_WEEKLY * 7))d" || true
else
    echo "[$(date -Iseconds)] ВНИМАНИЕ: BACKUP_REMOTE_BUCKET пуст — бэкап остался только на этой машине" >&2
fi

# --- Локальная чистка -----------------------------------------------------
echo "[$(date -Iseconds)] Удаляю локальные ежедневные старше ${KEEP_DAILY} дн., еженедельные старше $((KEEP_WEEKLY * 7)) дн."
find "$BACKUP_DIR" -maxdepth 1 -name 'lms-*.dump' -mtime "+${KEEP_DAILY}" -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'files-*.tar.gz' -mtime "+${KEEP_DAILY}" -delete
find "$BACKUP_DIR/weekly" -name 'lms-*.dump' -mtime "+$((KEEP_WEEKLY * 7))" -delete
find "$BACKUP_DIR/weekly" -name 'files-*.tar.gz' -mtime "+$((KEEP_WEEKLY * 7))" -delete

echo "[$(date -Iseconds)] Готово"
