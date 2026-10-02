# Запуск в Docker и деплой на Linux (D6.5)

Схема: два контейнера (`app` — gunicorn с приложением, `nginx` — вход и статика), PostgreSQL снаружи compose.

```
браузер ──► nginx :5085 ──► /static/…  файлы с диска (bind mount)
                       └──► всё остальное ──► app :8000 (gunicorn, 1 процесс, 8 потоков)
                                                  └──► PostgreSQL на хосте (host.docker.internal:5432)
```

## Что нужно на машине
- Docker Engine + Compose v2 (Linux) или Docker Desktop (Windows, WSL2).
- PostgreSQL с базой `hcmr_demo` (или рабочей `hcmr`) и ролью приложения `dashboard_app` (владелец схемы `app`, чтение витрин хранилища).
- PostgreSQL принимает подключения из контейнеров:
  - Docker Desktop: подключение к `host.docker.internal` приходит на хост через прокси Docker, обычно как с `127.0.0.1`. Проверка — ниже.
  - Linux: контейнеры ходят с адресов сети Docker (по умолчанию `172.16.0.0/12`). Нужно `listen_addresses`, включающий адрес моста `docker0` (например `'localhost,172.17.0.1'`), и строка в `pg_hba.conf`:
    ```
    host  hcmr_demo  dashboard_app  172.16.0.0/12  scram-sha-256
    ```
    Никогда не `trust`: такая строка пускает без пароля любого, кто пришёл с этих адресов.

## Ресурсы
Замер прогрева на демо-базе (Docker Desktop, 4 ядра, 8 ГБ): Sales, Stock и Delivery строятся за **~2 мин**, пик памяти контейнера **3.8 ГБ**, после прогрева **2.9 ГБ** (включая файловый кэш), своп не используется. Сборка занимает одно ядро: pandas и GIL работают в одном потоке. Остальные ядра обслуживают запросы и PartsData.

Минимум для сервера: 2 ядра и 6 ГБ памяти на контейнер. На Docker Desktop память и ядра ограничивает `%USERPROFILE%\.wslconfig` (`memory`, `processors`). С `memory=2GB`, `processors=1` тот же прогрев шёл больше 8 минут в свопе.

## Файлы, которых нет в git
| Файл | Содержимое |
|---|---|
| `.env` | `SECRET_KEY`, настройки отчётов (группы, склады), почта, получатели рассылок — как для dev-сервера |
| `secrets/pgpass` | одна строка формата libpq: `host.docker.internal:5432:hcmr_demo:dashboard_app:<пароль>` |

Пароль к базе живёт только в `secrets/pgpass`: не в `.env`, не в `DATABASE_URL`, не в образе. Compose монтирует файл в `/run/secrets/pgpass`, а `docker-entrypoint.sh` копирует его в `~/.pgpass` с правами 600. Файл с более широкими правами libpq молча игнорирует.

Compose задаёт ещё две переменные поверх `.env`:
- `DEBUG: "False"`: контейнер всегда работает в `ProductionConfig`, даже если `.env` скопирован с машины разработчика, где `DEBUG=True`.
- `TZ` из `DOCKER_TZ` в `.env` (например `Area/City`, как `SHOW timezone` у сервера PostgreSQL; без неё UTC): «сегодня» в отчётах и `REPORT_REFRESH_TIME` считаются в местном времени, а контейнер по умолчанию живёт в UTC. При разнице с UTC в 3 часа обновление в 06:00 случилось бы в 09:00. Имя не `TZ`: python-dotenv выставил бы `TZ` и dev-серверу на Windows, где формат `Area/City` не понимается.

Адрес базы для контейнера задаёт `DOCKER_DATABASE_URL`: переменная окружения или строка в `.env`. По умолчанию `postgresql+psycopg://dashboard_app@host.docker.internal:5432/hcmr_demo`. `DATABASE_URL` из `.env` остаётся адресом для dev-сервера.

## Запуск
```bash
docker compose up -d --build        # сборка ~3-5 мин в первый раз, потом секунды
docker compose logs -f app          # "Booting worker with pid" = gunicorn поднялся
# http://localhost:5085
```
После правки `.env` нужен `docker compose up -d --force-recreate app`: compose сравнивает конфигурацию сервиса, а не содержимое `env_file`, и без флага оставит контейнер со старым окружением.

Проверка подключения к базе и того, что пароль действительно спрашивается:
```bash
docker compose exec app python -c "from dashboard import create_app, db; from sqlalchemy import text; app = create_app(); ctx = app.app_context(); ctx.push(); print(db.session.execute(text('select current_user, inet_client_addr()')).one())"
```
Адрес клиента должен попадать под строку `pg_hba.conf` со `scram-sha-256`, а не с `trust`.

Первый администратор, если база новая:
```bash
docker compose exec app flask --app wsgi init-db
docker compose exec -it app flask --app wsgi create-admin admin     # пароль вводится интерактивно
```

## Рассылка по расписанию
Cron на хосте запускает команду внутри работающего контейнера:
```cron
0 7 * * 1-5  cd /opt/dashboard && docker compose exec -T app flask --app wsgi send-reports >> /var/log/dashboard/send-reports.log 2>&1
```
Код выхода 1 при ошибке. Вручную — кнопки на странице Sales.

## Деплой на Linux-сервер
```bash
sudo mkdir -p /opt/dashboard && sudo chown "$USER" /opt/dashboard
git clone <репозиторий> /opt/dashboard && cd /opt/dashboard
# положить .env и secrets/pgpass (chmod 600 secrets/pgpass)
docker compose up -d --build
```
Обновление: `git pull && docker compose up -d --build`. Пересобирается только слой с кодом, зависимости берутся из кэша, пока не менялся `uv.lock`.

**HTTPS.** Вне `DEBUG` cookie сессии помечены `Secure` (`ProductionConfig`): браузер отправляет их только по HTTPS. Исключение — `http://localhost`, поэтому локальная проверка работает. На сервере нужен TLS в nginx: сертификат (корпоративный CA или Let's Encrypt), `listen 443 ssl`, редирект с 80. Без него вход на сайт не заработает.

**Данные между пересборками.** Загруженный файл Delivery лежит в instance-папке приложения, в томе `instance` (`/app/instance/delivery/tracing.xlsx`). Бюджет и стоп-лист хранятся в базе. Excel разбивки для рассылки собирается в памяти, на диск не пишется. Переход со старого тома `delivery-uploads`: загрузить файл трассировки заново на странице Delivery (или скопировать его в `delivery/` нового тома) и удалить старый том: `docker volume rm <проект>_delivery-uploads`.

## Почему так
- **uv + `uv.lock`**: в образ попадают ровно те версии, что прошли тесты. Сначала копируются только `pyproject.toml` и `uv.lock`, поэтому слой зависимостей (~100 МБ колёс) пересобирается только при их изменении.
- **Один процесс gunicorn, потоки** (`gthread`): состояние отчётов живёт в памяти процесса. Каждый процесс строил бы и держал свою копию. Отдельные процессы на отчёт не делаем.
- **Не root** в контейнере: писать можно только в `/app/instance` (путь меняет переменная `INSTANCE_PATH`).
- **`.dockerignore`**: в образ не попадают `.env`, `secrets/`, `.git` и `instance/`. На машине разработчика там лежат рабочие файлы, а удалённый в следующем слое файл остаётся в предыдущем слое образа.
