#!/bin/sh
# Пересъёмка экранов, на которых каталог нашёл непереведённое или сломанную вёрстку.
set -u
cd "$(dirname "$0")"
python3 build_i18n_keys.py
ONLY="/school-settings,/table"
for lang in kk en; do
  ( cd .. && docker compose exec -T backend python manage.py reset_data --all --confirm "УДАЛИТЬ ДАННЫЕ" )
  SCREEN_WALK=1 WALK_MODE=catalog WALK_STATE=filled CATALOG_LANG=$lang CATALOG_ONLY="$ONLY" ./run.sh \
    --project=seed --project=screen-walk tests/seed.spec.ts tests/screen-walk.spec.ts
  echo "lang=$lang exit=$?"
done
echo "all-done"
