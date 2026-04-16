## Установка

```powershell
pip install -r requirements.txt
```

## Настройка

Создай в корне файл `.env`:

```env
ROBLOX_COOKIE=твой_куки_сюда
```

Основные настройки лежат в [src/constants.py](src/constants.py):

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
