#!/bin/sh
# Прогон браузерных проверок с гарантированной уборкой.
#
# Одноразовые записи прогона заводятся в globalSetup и убираются в globalTeardown.
# Но teardown не выполняется, если процесс убит снаружи (kill -9, закрытый
# терминал, упавшая машина) — а записи с паролем из .env не должны пережить
# прогон ни при каком исходе. Поэтому уборка продублирована ловушкой на выход:
# она отрабатывает и после падения тестов, и после обрыва.
set -u
cd "$(dirname "$0")"

cleanup() {
  ( cd .. && docker compose exec -T backend python manage.py purge_probe_users ) || true
  rm -rf .auth
}
trap cleanup EXIT INT TERM

npx playwright test "$@"
