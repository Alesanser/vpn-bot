# VPN Telegram Bot (aiogram + PostgreSQL + Telegram Stars)

Бот продаёт VPN-подписку за Telegram Stars, выдаёт ключи, продлевает подписку, ведёт базу пользователей и ключей, присылает напоминания.

## Возможности
- Оплата Telegram Stars (Invoice)
- Автовыдача ключа
- Продление без смены ключа
- Админка: список ключей и пользователей
- Автоосвобождение ключей после окончания подписки
- Напоминания за 3 дня и за 1 день до окончания

## Установка
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


##Настройка окружения
cp .env.example .env
nano .env

##Заполни:

BOT_TOKEN — токен от @BotFather

ADMIN_ID — твой Telegram user_id

параметры PostgreSQL

PostgreSQL

Создай базу и пользователя, либо используй свои.
Таблицы создаются автоматически при запуске бота.

Запуск
python bot.py

Админ-команды

/add ss://KEY — добавить ключ

/del N — удалить ключ по номеру из списка

/support — показать контакты админа


---
