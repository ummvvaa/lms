#!/bin/sh
# Каталог экранов на казахском и английском: посев наполненной школы и обход
# всех ролей на 1440 и 390 с проверкой перевода (`helpers/i18n-audit.ts`).
# Два прохода подряд — у каждого свой посев: `run.sh` убирает записи прогона.
set -u
cd "$(dirname "$0")"
python3 build_i18n_keys.py
for lang in kk en; do
  ( cd .. && docker compose exec -T backend python manage.py reset_data --all --confirm "УДАЛИТЬ ДАННЫЕ" )
  SCREEN_WALK=1 WALK_MODE=catalog WALK_STATE=filled CATALOG_LANG=$lang ./run.sh \
    --project=seed --project=screen-walk tests/seed.spec.ts tests/screen-walk.spec.ts
  echo "lang=$lang exit=$?"
done
echo "all-done"
