import os
import math
import string
import random
from datetime import datetime

from src.ansi import ANSI
from src.date import current_datetime


def cls() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


def generate_launch_time() -> int:
    return math.floor((datetime.now() - datetime(1970, 1, 1)).total_seconds() * 1000)


def generate_browser_tracker_id() -> str:
    return str(random.randint(100000, 175000)) + str(random.randint(100000, 900000))


def log(message: str, color: str = ANSI.WHITE) -> None:
    print(
        f"{current_datetime()} "
        f"| {color}{message}{ANSI.WHITE}"
    )
