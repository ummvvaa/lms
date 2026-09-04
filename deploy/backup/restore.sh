#!/bin/sh
# Развернуть бэкап в рабочую базу. Осознанно требует подтверждения:
# восстановление затирает текущие данные.
#
# Использование:
#   restore.sh                                   — показать, что есть локально и в хранилище
#   restore.sh lms-YYYYmmdd-HHMMSS.dump --force  — восстановить; если файла нет
#                                                  локально, он скачивается из хранилища
#
# Имя файла достаточно без пути: скрипт ищет в /backups, затем в weekly/,
# затем в хранилище (daily/, потом weekly/).
set -eu

# доступ к базе — из тех же переменных, что у самого Postgres в env_file
export PGHOST="${PGHOST:-postgres}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-lms}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-lms}}"

BACKUP_DIR="${BACKUP_DIR:-/backups}"

remote_ready() {
    [ -n "${BACKUP_REMOTE_BUCKET:-}" ]
}

remote_setup() {
    export RCLONE_CONFIG_STORE_TYPE=s3
    export RCLONE_CONFIG_STORE_PROVIDER="${BACKUP_REMOTE_PROVIDER:-Other}"
    export RCLONE_CONFIG_STORE_ENDPOINT="${BACKUP_REMOTE_ENDPOINT:-}"
    export RCLONE_CONFIG_STORE_REGION="${BACKUP_REMOTE_REGION:-}"
    export RCLONE_CONFIG_STORE_ACCESS_KEY_ID="${BACKUP_REMOTE_ACCESS_KEY:-}"
    export RCLONE_CONFIG_STORE_SECRET_ACCESS_KEY="${BACKUP_REMOTE_SECRET_KEY:-}"
    REMOTE="store:${BACKUP_REMOTE_BUCKET}/${BACKUP_REMOTE_PREFIX:-lms}"
}

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "Использование: restore.sh lms-YYYYmmdd-HHMMSS.dump --force" >&2
    echo >&2
    echo "Локально (${BACKUP_DIR}):" >&2
    ls -1t "$BACKUP_DIR"/lms-*.dump "$BACKUP_DIR"/weekly/lms-*.dump 2>/dev/null | head -20 >&2 || true
    if remote_ready; then
        remote_setup
        echo >&2
        echo "В хранилище (${REMOTE}):" >&2
        rclone lsf "$REMOTE/daily/" --include 'lms-*.dump' 2>/dev/null | sort -r | head -10 >&2 || true
        rclone lsf "$REMOTE/weekly/" --include 'lms-*.dump' 2>/dev/null | sort -r | head -10 >&2 || true
    else
        echo >&2
        echo "Хранилище не настроено (BACKUP_REMOTE_BUCKET пуст)" >&2
    fi
    exit 1
fi

BASE="$(basename "$NAME")"
STAMP=$(echo "$BASE" | sed -e 's/^lms-//' -e 's/\.dump$//')
FILES_BASE="files-${STAMP}.tar.gz"

# --- Найти дамп: локально, потом в хранилище --------------------------------
FILE=""
for candidate in "$NAME" "$BACKUP_DIR/$BASE" "$BACKUP_DIR/weekly/$BASE"; do
    if [ -f "$candidate" ]; then
        FILE="$candidate"
        break
    fi
done

if [ -z "$FILE" ]; then
    if ! remote_ready; then
        echo "ОШИБКА: файл $BASE не найден локально, а хранилище не настроено" >&2
        exit 1
    fi
    remote_setup
    mkdir -p "$BACKUP_DIR/restore"
    for folder in daily weekly; do
        if rclone lsf "$REMOTE/$folder/" --include "$BASE" 2>/dev/null | grep -q .; then
            echo "[$(date -Iseconds)] Скачиваю ${BASE} из ${REMOTE}/${folder}/"
            rclone copy "$REMOTE/$folder/$BASE" "$BACKUP_DIR/restore/"
            rclone copy "$REMOTE/$folder/$FILES_BASE" "$BACKUP_DIR/restore/" 2>/dev/null || true
            FILE="$BACKUP_DIR/restore/$BASE"
            break
        fi
    done
fi

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "ОШИБКА: файл $BASE не найден ни локально, ни в хранилище" >&2
    exit 1
fi

if [ "${2:-}" != "--force" ]; then
    echo "Найден: ${FILE}"
    echo "ВНИМАНИЕ: восстановление затрёт текущее содержимое базы ${PGDATABASE}."
    echo "Повторите с флагом --force, если это то, что нужно."
    exit 1
fi

echo "[$(date -Iseconds)] Восстанавливаю ${FILE} в ${PGDATABASE}"
pg_restore --dbname="$PGDATABASE" --clean --if-exists --no-owner --no-privileges "$FILE"
echo "[$(date -Iseconds)] База восстановлена"

# --- Загруженные файлы -----------------------------------------------------
# Рядом с дампом лежит архив файлов того же времени. Без него материалы
# олимпиадников и документы портфолио останутся ссылками в пустоту.
FILES="$(dirname "$FILE")/$FILES_BASE"
if [ -f "$FILES" ]; then
    echo "[$(date -Iseconds)] Разворачиваю файлы из ${FILES}"
    tar -xzf "$FILES" -C /app
    echo "[$(date -Iseconds)] Файлы восстановлены"
else
    echo "ПРЕДУПРЕЖДЕНИЕ: архива файлов ${FILES_BASE} нет — восстановлена только база" >&2
fi

echo "[$(date -Iseconds)] Восстановление завершено. Перезапустите backend и celery-worker"
