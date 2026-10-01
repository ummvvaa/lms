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
  # карточки, заведённые прогоном, помечаются вымышленными (фаза 64): по этому
  # признаку `preflight` их находит, а `purge_fictional` вычищает
  ( cd .. && docker compose exec -T backend python manage.py mark_fictional --domain probe.local --yes ) || true
  ( cd .. && docker compose exec -T backend python manage.py purge_probe_users ) || true
  rm -rf .auth
}
trap cleanup EXIT INT TERM

# Точечный перегон: ./run.sh --spot tests/curator-cabinet.spec.ts
# После полного прогона в базе эталонная или пустая школа — сценарии на ней
# краснеют на данных. Ключ обнуляет базу, сеет заново и гонит указанное.
# Проекты идут в порядке конфига: сначала посев, потом сценарии
if [ "${1:-}" = "--spot" ]; then
  shift
  SEED_FRESH=1 npx playwright test --project=seed --project=chromium tests/seed.spec.ts "$@"
  exit $?
fi

npx playwright test "$@"
