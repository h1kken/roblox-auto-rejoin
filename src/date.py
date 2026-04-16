from datetime import datetime


def current_datetime() -> str:
    return datetime.now().strftime('%d.%m.%Y - %H:%M:%S')
