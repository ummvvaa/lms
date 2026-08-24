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

## 2. Сертификат TLS

Выпуск делается один раз руками, дальше сертификат продлевается сам.

**Шаг 1. Поднять контур с самоподписанным сертификатом.** Nginx не стартует
без файла сертификата, а Let's Encrypt не выпустит его, пока nginx не отвечает
на 80 порту. Разрываем круг заглушкой:

```bash
mkdir -p deploy/certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -subj "/CN=school.kz" \
  -keyout deploy/certs/privkey.pem -out deploy/certs/fullchain.pem
```

В `deploy/.env.prod` временно указать заглушку:

```
SSL_CERT_PATH=/etc/nginx/certs/fullchain.pem
SSL_KEY_PATH=/etc/nginx/certs/privkey.pem
```

Поднять контур (шаг 3) и убедиться, что домен открывается по http
(браузер будет ругаться на сертификат — так и должно быть).

**Шаг 2. Выпустить настоящий сертификат:**

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  certonly --webroot --webroot-path=/var/www/certbot \
  -d school.kz -d www.school.kz \
  --email admin@school.kz --agree-tos --no-eff-email
```

**Шаг 3. Убрать заглушку.** Закомментировать `SSL_CERT_PATH` и `SSL_KEY_PATH`
в `deploy/.env.prod` — тогда nginx возьмёт живой сертификат из тома certbot
(`/etc/letsencrypt/live/$SERVER_NAME/`), — и перезапустить nginx:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d nginx
```

### Продление

Продлевает служба `certbot`: она просыпается дважды в сутки и обновляет
сертификат, когда до истечения остаётся меньше 30 дней. Nginx перечитывает
конфиг раз в шесть часов и подхватывает новый файл сам — перезапускать
контур не нужно. Ручное продление раз в три месяца всё равно бы забылось.

**Проверить, что механизм работает** (делается сразу после первого выпуска,
пробный прогон настоящий сертификат не трогает):

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  renew --webroot --webroot-path=/var/www/certbot --dry-run
```

Должно закончиться строкой `Congratulations, all simulated renewals succeeded`.
Служба `certbot` делает такой же прогон при каждом старте и пишет результат
в свой лог и в `/etc/letsencrypt/renew.log`:

```bash
docker compose -f deploy/docker-compose.prod.yml logs certbot | tail -20
```

Если пробный прогон не проходит — почти всегда закрыт 80 порт снаружи
или домен смотрит не на этот сервер.

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

**База стартует пустой** — это инвариант, никаких выдуманных учеников.
Данные заводятся импортом и руками:

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python manage.py import_students /app/media/students.xlsx
```

Команды `create_dev_users`, `seed_demo` и `seed_prep` в боевом контуре
не работают: они отказываются запускаться при `DEBUG=0`. Учётные записи
заводит администратор на экране «Пользователи»: он создаёт запись
и отправляет ссылку, а пароль владелец задаёт себе сам.

### Стартовый справочник вузов — по желанию

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python manage.py seed_universities
```

Команда заводит 20 вузов с программами, требованиями и раундами.

> **Это заготовка, а не проверенные данные.** Пороги и дедлайны собраны
> из открытых источников и помечены признаком «не подтверждено»: над
> каждой такой записью в интерфейсе висит оранжевая плашка, и ученику
> процент соответствия по ней показывается с той же оговоркой. Снимает
> плашку директор по поступлению после сверки с сайтом вуза.
>
> Команда **не запускается автоматически** ни при выкате, ни при старте
> контейнера. Если школа ведёт свой справочник — её можно не запускать
> вовсе, а уже заведённую заготовку убрать: `drop_seed_catalog` или
> кнопка «Удалить стартовый справочник» на экране «Справочник».

## 5. Проверка после выката

```bash
curl -fsS https://school.kz/healthz   # {"status":"ok"} — процесс жив
curl -fsS https://school.kz/readyz    # база и Redis доступны
docker compose -f deploy/docker-compose.prod.yml ps
```

`healthz` не ходит в базу и годится для балансировщика. `readyz` проверяет
Postgres и Redis и отдаёт 503, если что-то отвалилось.

## Бэкапы

Контейнер `backup` по расписанию (`BACKUP_INTERVAL_SECONDS`, по умолчанию
сутки) делает две вещи:

1. снимает дамп базы и **сразу проверяет восстановление** во временную базу —
   непроверенный бэкап это не бэкап, а надежда;
2. складывает загруженные файлы (`media` и закрытый `private` с материалами
   олимпиадников) в архив `files-<метка>.tar.gz` и проверяет, что архив
   читается. База без файлов — половина бэкапа: карточки будут ссылаться
   в пустоту.

Хранится `BACKUP_KEEP_DAYS` поколений (по умолчанию 14), старые удаляются.
Результат каждой проверки пишется в `/backups/verified.log`.

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
  sh -c 'cp /b/lms-*.dump /b/files-*.tar.gz /out/'
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

**ИИ-разбор не работает.** Две причины, и обе видны на экране «Расходы
на ИИ» у администратора. Либо пустой `LLM_API_KEY` — тогда система работает
правилами: разбор идёт шаблонами, объяснения собираются из движка
соответствия, и это рабочий режим, а не поломка. Либо выбран месячный
лимит `LLM_MONTHLY_LIMIT` — операции с моделью отключаются до первого числа,
остальное продолжает работать.

**Сертификат не продлился.** `logs certbot` покажет причину. Чаще всего
снаружи закрыт 80 порт: проверка Let's Encrypt ходит именно на него,
и без неё продления не будет.

## Подключение модели

Ключ и модель задаются переменными окружения и нигде больше:

| Переменная | Что это |
|---|---|
| `LLM_PROVIDER` | `anthropic` или `none` — второй отключает модель совсем |
| `LLM_API_KEY` | ключ провайдера. Пусто — система работает правилами |
| `LLM_MODEL` | название модели |
| `LLM_MONTHLY_LIMIT` | месячный лимит расходов в долларах. Ноль — без лимита |
| `LLM_PRICE_INPUT`, `LLM_PRICE_OUTPUT` | цена за миллион токенов, для подсчёта расходов |
| `LLM_RATE` | предел частоты обращений, по умолчанию `20/min` |

Каждый вызов записывается: кто, когда, какая операция, сколько токенов
и денег. Смотреть — экран «Расходы на ИИ» у администратора.

Режим без хранения запросов на стороне провайдера включён по умолчанию
(`LLM_NO_RETENTION=1`). В модель уходят только поля, нужные операции;
вместо имён учеников отправляются номера, имена подставляются обратно
на сервере.
