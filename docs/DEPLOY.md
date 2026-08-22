# Развёртывание на боевом сервере

Контур поднимается через Docker Compose на своём VPS. Всё, что описано ниже,
проверено на файлах в `deploy/`.

## Что потребуется

- VPS с Docker 24+ и Docker Compose v2
- Домен, направленный A-записью на сервер
- SMTP-доступ: на почту уходят приглашения, ссылки на сброс пароля и вход выпускников

## 1. Забрать код и настроить окружение

```bash
git clone <репозиторий> /opt/lms && cd /opt/lms
cp deploy/.env.prod.example deploy/.env.prod
```

Заполнить `deploy/.env.prod`. Обязательные поля, без которых контур не поднимется:

| Переменная | Что это |
|---|---|
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_ALLOWED_HOSTS` | домены через запятую |
| `CSRF_TRUSTED_ORIGINS` | те же домены со схемой `https://` |
| `SERVER_NAME` | домен для nginx |
| `POSTGRES_PASSWORD` | пароль базы |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP: без него приглашения не уйдут |

`deploy/.env.prod` в git не попадает — он в `.gitignore`.

## 2. Сертификаты TLS

```bash
docker run --rm -p 80:80 \
  -v /opt/lms/deploy/certs:/etc/letsencrypt/live/school.kz \
  certbot/certbot certonly --standalone -d school.kz -d www.school.kz
```

Nginx ждёт `deploy/certs/fullchain.pem` и `deploy/certs/privkey.pem`.
Продление — cron на хосте раз в месяц с `docker compose ... restart nginx` после.

## 3. Запуск

```bash
docker compose -f deploy/docker-compose.prod.yml up -d
```

Что поднимется: `postgres`, `redis`, `backend` (gunicorn), `celery-worker`,
`celery-beat`, `nginx` с TLS, `backup`. Контейнер `frontend-build` соберёт
статику фронта и завершится — так и задумано.

Миграции накатываются автоматически из `entrypoint.sh` при старте `backend`.

## 4. Первый вход

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python manage.py createsuperuser
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python manage.py collectstatic --noinput
```

**База стартует пустой** — это инвариант, никаких демо-учеников.
Данные заводятся импортом и руками:

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python manage.py import_students /app/media/students.xlsx
```

## 5. Проверка после выката

```bash
curl -fsS https://school.kz/healthz   # {"status":"ok"} — процесс жив
curl -fsS https://school.kz/readyz    # база и Redis доступны
docker compose -f deploy/docker-compose.prod.yml ps
```

`healthz` не ходит в базу и годится для балансировщика. `readyz` проверяет
Postgres и Redis и отдаёт 503, если что-то отвалилось.

## Бэкапы

Контейнер `backup` снимает дамп по расписанию (`BACKUP_INTERVAL_SECONDS`,
по умолчанию сутки) и **сразу проверяет восстановление** во временную базу:
непроверенный бэкап — это не бэкап, а надежда. Результат каждой проверки
пишется в `/backups/verified.log`.

Снять бэкап вручную:

```bash
docker compose -f deploy/docker-compose.prod.yml exec backup /scripts/backup.sh
```

Посмотреть, что есть:

```bash
docker compose -f deploy/docker-compose.prod.yml exec backup ls -lt /backups
docker compose -f deploy/docker-compose.prod.yml exec backup cat /backups/verified.log
```

Восстановить (затирает текущие данные, поэтому нужен `--force`):

```bash
docker compose -f deploy/docker-compose.prod.yml exec backup \
  /scripts/restore.sh /backups/lms-20260821-030000.dump --force
docker compose -f deploy/docker-compose.prod.yml restart backend celery-worker
```

Файлы лежат в томе `backups`. **Забирайте их с сервера наружу** — бэкап,
лежащий на той же машине, не спасает от потери машины:

```bash
docker run --rm -v lms-prod_backups:/b -v /mnt/external:/out alpine \
  sh -c 'cp /b/lms-*.dump /out/'
```

### Восстановление на чистой машине

Проверено ровно этим порядком действий:

```bash
docker run -d --name pg -e POSTGRES_DB=lms -e POSTGRES_USER=lms \
  -e POSTGRES_PASSWORD=lms postgres:16-alpine
docker run --rm --network <сеть> -e PGHOST=pg -e PGUSER=lms \
  -e PGPASSWORD=lms -e PGDATABASE=lms \
  -v /opt/lms/deploy/backup:/scripts:ro -v <том с бэкапами>:/backups \
  postgres:16-alpine /scripts/restore.sh /backups/<файл>.dump --force
```

## Фоновые задачи

`celery-beat` держит расписание (`CELERY_BEAT_SCHEDULE` в `config/settings/base.py`):

| Задача | Когда | Что делает |
|---|---|---|
| `universities.sync_deadlines` | 03:00 ежедневно | Сверяет дедлайны по белому списку доменов, расхождения складывает в `Suggestion` |
| `universities.promote_graduates` | 04:00 ежедневно | Переводит учеников в выпускники по дате выпуска |
| `core.snapshot_readiness` | 02:00 по понедельникам | Недельный срез Readiness для графиков |

Сверка ходит **только** по сайтам вузов из справочника и Common App.
Домен вуза берётся из поля `University.domain` — если оно пустое, вуз
не сверяется. Дополнительные разрешённые хосты — `SYNC_EXTRA_HOSTS`.

Ни одна задача не меняет доменные поля сама: всё уходит в предложения,
применяет человек.

## Логи и наблюдаемость

Логи идут в stdout, ротацию делает Docker (`max-size: 20m`, `max-file: 5`,
задано в боевом compose). Смотреть:

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f backend
docker compose -f deploy/docker-compose.prod.yml logs -f celery-worker
```

Sentry включается заполнением `SENTRY_DSN`. Персональные данные учеников
в трассировки не отправляются (`send_default_pii=False`).

## Обновление версии

```bash
cd /opt/lms && git pull
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
```

Миграции накатятся при старте. Перед обновлением снимите бэкап вручную —
он проверяется автоматически, но лучше иметь свежий.

## Откат

```bash
git checkout <предыдущий тег>
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Если миграция необратима — восстановить базу из бэкапа, снятого перед выкатом.

## Частые проблемы

**`backend` перезапускается.** Смотреть `logs backend`: чаще всего не задан
`DJANGO_SECRET_KEY` или недоступен Postgres.

**502 от nginx.** `backend` ещё не прошёл healthcheck. `readyz` покажет, что
именно не поднялось — база или Redis.

**Письма со ссылками не приходят.** Проверить `EMAIL_*`; при пустом
`EMAIL_HOST` бэкенд почты пишет письма в лог, а не отправляет.

**Никто не может войти в свежий контур.** Учётные записи заводит
администратор — самостоятельной регистрации нет. Первого администратора
создаёт `python manage.py createsuperuser`; дальше он приглашает остальных
с экрана «Пользователи».

**Человек не получил приглашение.** Ссылка живёт час
(`PASSWORD_LINK_TTL_MINUTES`). Выслать заново — кнопка «Выслать ссылку»
в списке пользователей. При пустом `EMAIL_HOST` письма уходят в лог.

**«Слишком много неудачных попыток».** После пяти неудач подряд учётная
запись запирается с нарастающей задержкой — от минуты до часа. Снять
блокировку раньше срока можно, удалив неудачные попытки этого адреса
в админке (раздел «Попытки входа»).

**ИИ-разбор не работает.** При пустом `LLM_API_KEY` система переходит
в офлайн-режим: разбор идёт правилами, объяснения собираются из движка
соответствия. Это рабочий режим, а не поломка.
