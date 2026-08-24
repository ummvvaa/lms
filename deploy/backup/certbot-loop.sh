#!/bin/sh
# Автопродление сертификата. Отдельный контейнер, а не cron на хосте:
# расписание уезжает вместе с контуром, и «продлю руками через три
# месяца» перестаёт быть планом.
#
# Первый выпуск делается вручную один раз (см. docs/DEPLOY.md);
# дальше эта служба продлевает сертификат сама. nginx перечитывает
# конфиг раз в шесть часов и подхватывает новый файл.
set -eu

INTERVAL="${CERTBOT_INTERVAL_SECONDS:-43200}"   # дважды в сутки
LOG="/etc/letsencrypt/renew.log"

note() {
    echo "[$(date -Iseconds)] $*"
    echo "[$(date -Iseconds)] $*" >> "$LOG" 2>/dev/null || true
}

note "Служба продления сертификата запущена, интервал ${INTERVAL} с"

# при старте — пробный прогон: если продление сломано, узнать об этом
# надо сейчас, а не за день до истечения срока
if [ "${CERTBOT_DRY_RUN_ON_START:-1}" = "1" ]; then
    if certbot renew --webroot --webroot-path=/var/www/certbot --dry-run >/dev/null 2>&1; then
        note "Пробное продление прошло: механизм рабочий"
    else
        note "ВНИМАНИЕ: пробное продление не прошло. Три обычные причины:"
        note "  1) сертификат ещё не выпускали — сделайте это один раз вручную (docs/DEPLOY.md, раздел 2)"
        note "  2) снаружи закрыт 80 порт — проверка Let's Encrypt ходит именно на него"
        note "  3) домен смотрит не на этот сервер"
    fi
fi

while true; do
    if certbot renew --webroot --webroot-path=/var/www/certbot --quiet; then
        note "Проверка продления завершена"
    else
        note "ОШИБКА: продление не отработало" >&2
    fi
    sleep "$INTERVAL"
done
