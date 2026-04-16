# roblox-auto-rejoin

Небольшой скрипт для авто-захода в нужный плейс Roblox, если аккаунт вылетел или не находится в игре.

## Что нужно

- Python 3.11+
- Установленный Fishstrap
- Cookie `.ROBLOSECURITY`

## Установка

```powershell
pip install -r requirements.txt
```

## Настройка

Создай в корне файл `.env`:

```env
ROBLOX_COOKIE=твой_куки_сюда
```

Основные настройки лежат в [src/constants.py](/d:/Desktop/Learning/Programming/.maintained/roblox-auto-rejoin/src/constants.py):

- `PLACE_NAME`
- `FIRSTLY_SMALL_SERVERS`
- `EXCLUDE_FULL_GAMES`
- `JOIN_TO_FRIENDS`
- `LIMIT_SERVERS_PER_PAGE`
- интервалы перепроверки

## Запуск

```powershell
python main.py
```

## Стек

- `aiohttp`
- `psutil`
- `python-dotenv`
