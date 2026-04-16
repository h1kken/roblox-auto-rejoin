import os
import asyncio
from dotenv import load_dotenv
from src.ansi import ANSI
from src.constants import (
    PLACE_ID,
    RECHECK_AFTER_LAUNCH_INTERVAL,
    RECHECK_PLAYER_IN_PLACE_INTERVAL,
)
from src.exceptions import InvalidCookie
from src.http import HttpClient
from src.process import RobloxLauncher
from src.roblox import get_user_info, get_place_id_user_in
from src.utils import cls, log
from src.constants import PATH_ROBLOX

load_dotenv()


async def main() -> None:
    cls()
    if PATH_ROBLOX:
        log(f"Detected Roblox path: {PATH_ROBLOX}", ANSI.GREEN)
    
    print(ANSI.BOLD, end="")

    cookie = os.getenv("ROBLOX_COOKIE")
    if cookie is None:
        raise InvalidCookie("No cookie found")

    cookies = {".ROBLOSECURITY": cookie}
    launcher = RobloxLauncher()

    log("Successfully got cookie from environment variable", ANSI.GREEN)

    async with HttpClient(cookies=cookies) as client:
        while True:
            try:
                user_id, name, display_name = await get_user_info(client)
                place_id = await get_place_id_user_in(client, user_id=user_id)
                if place_id == PLACE_ID:
                    log(f"{name} is already in the game (id: {PLACE_ID})", ANSI.GREEN)
                    await asyncio.sleep(RECHECK_PLAYER_IN_PLACE_INTERVAL)
                    continue

                log(f"{name} is joining... (id: {PLACE_ID})", ANSI.YELLOW)
                await launcher.launch(client)
                await asyncio.sleep(RECHECK_AFTER_LAUNCH_INTERVAL)
            except Exception as error:
                log(f"An unexpected error occurred: {error}", ANSI.RED)
                await asyncio.sleep(RECHECK_AFTER_LAUNCH_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
