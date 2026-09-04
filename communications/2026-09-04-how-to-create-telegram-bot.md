<!-- Internal how-to for Ralina, not client-facing. Kept in Russian per her preference (working notes). -->

# Как создать Telegram-бота и получить токен

Нужно один раз, займёт 2 минуты.

1. Открой Telegram, найди `@BotFather` (официальный бот Telegram, синяя галочка).
2. Напиши ему `/newbot`.
3. Он спросит **имя бота** (отображается в чате, можно кириллицей) — например: `Проверка кандидатов`.
4. Он спросит **username бота** (должен заканчиваться на `bot`, латиницей, без пробелов) — например: `candidate_screening_bot`. Если занято — придумай другой, вариантов много.
5. BotFather пришлёт сообщение вида:
   ```
   Done! Congratulations on your new bot...
   Use this token to access the HTTP API:
   123456789:AAExampleTokenStringHere
   ```
   Это и есть `TELEGRAM_BOT_TOKEN`. Скопируй строку после "Use this token to access the HTTP API:".
6. Вставь его в `prototype/.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAExampleTokenStringHere
   ```
7. Запусти бота: `cd prototype && python main.py` (или `.venv/Scripts/python main.py`, если venv не активирован).
8. В Telegram найди своего бота по username (`@candidate_screening_bot`) и напиши `/start` — бот ответит приветствием, дальше присылай вакансию (ссылку hh.ru или текст) и резюме (файл или текст) в любом порядке.

## Не обязательно, но полезно

- **Описание/аватар бота** — необязательно для прототипа, но если хочешь: `/setdescription`, `/setuserpic` в BotFather.
- **Токен — это секрет**, как пароль. Не коммить его в git (`.env` уже в `.gitignore` — проверь `git status` перед коммитом, если вдруг добавляла `.env` руками).
- Если токен утёк (например, случайно закоммитила) — в BotFather есть `/revoke` для перевыпуска токена того же бота.
- Каждый бот привязан к одному Telegram-аккаунту (тому, что писал BotFather). Если хочешь, чтобы Антон тоже мог тестировать — просто дай ему username бота, боты в Telegram публичны по умолчанию (если не поставить приватность через BotFather `/setjoingroups` и т.п., что тут не нужно).
