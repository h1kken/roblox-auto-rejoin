import os
import asyncio
import threading
from dotenv import load_dotenv
from pynput import keyboard
from src.ansi import ANSI
from src.config import get_rejoin_if_in_other_place, set_rejoin_if_in_other_place
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

REJOIN_IF_IN_OTHER_PLACE = threading.Event()


def start_rejoin_toggle_listener() -> None:
    def on_release(key: keyboard.Key) -> None:
        try:
            if key.char is None or key.char.lower() != "r":
                return
        except AttributeError:
            return

        enabled = not REJOIN_IF_IN_OTHER_PLACE.is_set()
        set_rejoin_if_in_other_place(enabled)
        if enabled:
            REJOIN_IF_IN_OTHER_PLACE.set()
            log(" [>] Rejoin if in other place is ENABLED", ANSI.YELLOW)
        else:
            REJOIN_IF_IN_OTHER_PLACE.clear()
            log(" [>] Rejoin if in other place is DISABLED", ANSI.YELLOW)

    listener = keyboard.Listener(on_release=on_release)
    listener.daemon = True
    listener.start()
    log(" [?] Press R to toggle rejoin if in other place", ANSI.YELLOW)


async def main() -> None:
    cls()
    if get_rejoin_if_in_other_place():
        REJOIN_IF_IN_OTHER_PLACE.set()
    else:
        REJOIN_IF_IN_OTHER_PLACE.clear()

    if not PATH_ROBLOX:
        log(" [!] Can\'t detect Roblox installation path\n", ANSI.RED)
        input(" [<] Press Enter to exit...")
        exit(1)
    
    log(f" {ANSI.BOLD}[+] Detected Roblox path: {PATH_ROBLOX}", ANSI.GREEN)
    
    cookie = os.getenv("ROBLOX_COOKIE")
    if cookie is None:
        raise InvalidCookie("No cookie found")

    cookies = {".ROBLOSECURITY": cookie}
    launcher = RobloxLauncher()

    log(" [+] Successfully got cookie from environment variable", ANSI.GREEN)
    log(
        f" [>] Rejoin if in other place is {'ENABLED' if REJOIN_IF_IN_OTHER_PLACE.is_set() else 'DISABLED'}",
        ANSI.YELLOW,
    )
    start_rejoin_toggle_listener()

    async with HttpClient(cookies=cookies) as client:
        while True:
            try:
                user_id, name, display_name = await get_user_info(client)
                place_id = await get_place_id_user_in(client, user_id=user_id)
                
                if place_id == PLACE_ID:
                    log(f"{name} is already in the game (id: {PLACE_ID})", ANSI.GREEN)
                    await asyncio.sleep(RECHECK_PLAYER_IN_PLACE_INTERVAL)
                    continue
                
                if place_id is None and not REJOIN_IF_IN_OTHER_PLACE.is_set():
                    log(
                        f"{name} is not in any place. Rejoin is disabled, continuing checks...",
                        ANSI.YELLOW,
                    )
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
