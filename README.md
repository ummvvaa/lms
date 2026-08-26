# Платформа подготовки к поступлению

Внутренняя платформа частной школы. Пять директоров ведут свои домены,
ученик видит свой кабинет. Данные заводятся импортом и руками, база
стартует пустой.

## Запуск для разработки

```bash
cp deploy/.env.example deploy/.env    # заполнить пароли
docker compose up
```

Фронт — http://localhost:5173, API — http://localhost:8000/api/,
документация API — http://localhost:8000/api/docs/.

Учётные записи всех ролей для разработки заводит команда
`python manage.py create_dev_users` — только при `DEBUG=1`, пароли берутся
из `deploy/.env`. Отключённые администратором записи команда не включает
обратно: для этого нужен явный ключ `--force`.

Браузерный прогон ходит не под ними, а под **одноразовыми записями**
`*@probe.local`: `e2e/run.sh` заводит их перед прогоном
(`create_probe_users`, пароль из `PROBE_PASSWORD` в `e2e/.env`) и убирает
насовсем после (`purge_probe_users`) — даже если прогон упал или был
прерван. После прогона в системе не остаётся ни одной лишней записи;
журнал правок остаётся с подписью автора.

## Проверки

```bash
docker compose exec backend pytest          # тесты
docker compose exec backend ruff check .    # линтер
docker compose exec backend black --check . # форматирование
cd e2e && npm test                          # браузерные сценарии (run.sh)
cd e2e && python3 api_probe.py              # прогон API под всеми ролями
```

## Документация

| Файл | О чём |
|---|---|
| [CLAUDE.md](CLAUDE.md) | правила проекта, инварианты и журнал решений |
| [docs/STATE.md](docs/STATE.md) | что сделано по фазам и что проверено |
| [docs/DEPLOY.md](docs/DEPLOY.md) | развёртывание на боевом сервере с нуля |
| [docs/ADMIN.md](docs/ADMIN.md) | руководство администратора школы |
| [docs/DEFECTS.md](docs/DEFECTS.md) | реестр находок и их закрытия |
| [docs/I18N.md](docs/I18N.md) | переводы: устройство, что не переводится, статус казахского |

## Структура

```
backend/    Django + DRF, приложения по доменам
frontend/   React + TypeScript + Vite
e2e/        Playwright и прогон API по ролям
deploy/     docker-compose, nginx, бэкапы, примеры окружения
docs/       документация
```
# lms
# lms
