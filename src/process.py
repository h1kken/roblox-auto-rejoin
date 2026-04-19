import asyncio
import os
import subprocess
import sys
from urllib.parse import quote

import psutil

from src.ansi import ANSI
from src.constants import PLACE_ID, PATH_ROBLOX, PROCESS_NAME, RECHECK_CHILD_PROCESSES_INTERVAL
from src.http import HttpClient
from src.roblox import get_auth_ticket, get_job_id
from src.utils import generate_browser_tracker_id, generate_launch_time, log


def get_child_processes(pid: int) -> list[psutil.Process]:
    try:
        parent = psutil.Process(pid)
        return parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


class RobloxLauncher:
    def __init__(self, pid: int | None = None) -> None:
        self._pid = pid

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def process_name(self) -> str:
        return PROCESS_NAME

    async def launch(
        self,
        client: HttpClient,
        *,
        place_id: int | None = None,
        server_id: str | None = None,
        auth_ticket: str | None = None,
        log_output: bool = True,
    ) -> bool:
        launch_time = generate_launch_time()
        browser_tracker_id = generate_browser_tracker_id()
        target_place_id = place_id or PLACE_ID

        if server_id is None:
            server_id = await get_job_id(client, place_id=target_place_id, log_output=log_output)

        if not server_id:
            if log_output:
                log("Failed to launch Roblox: server_id is missing", ANSI.RED)
            return False

        launch_url = quote(
            f"https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGame"
            f"&placeId={target_place_id}"
            f"&gameId={server_id}"
            f"&isPlayTogetherGame=true"
            f"&isTeleport=true"
        )

        if auth_ticket is None:
            auth_ticket = await get_auth_ticket(client, log_output=log_output)

        if not auth_ticket:
            if log_output:
                log("Failed to launch Roblox: auth_ticket is missing", ANSI.RED)
            return False

        arguments = (
            f"roblox-player:1"
            f"+launchmode:play"
            f"+gameinfo:{auth_ticket}"
            f"+launchtime:{launch_time}"
            f"+placelauncherurl:{launch_url}"
            f"+browsertrackerid:{browser_tracker_id}"
            f"+robloxLocale:en_us"
            f"+gameLocale:en_us"
            f"+channel:"
            f"+LaunchExp:InApp"
        )

        if not sys.platform.startswith("win"):
            return False

        if self._pid is not None:
            self.kill()

        try:
            process = subprocess.Popen([os.path.expandvars(PATH_ROBLOX), arguments])
        except Exception as e:
            if log_output:
                log(f" [!] Failed to launch Roblox: {e}", ANSI.RED)
            return False

        while True:
            child_processes = get_child_processes(process.pid)
            if not child_processes:
                await asyncio.sleep(RECHECK_CHILD_PROCESSES_INTERVAL)
                continue

            for child_process in child_processes:
                if PROCESS_NAME in child_process.name().lower():
                    self._pid = child_process.pid
            break

        return True

    def kill(self, *, log_output: bool = True) -> None:
        if self._pid is None:
            return

        try:
            psutil.Process(self._pid).terminate()
        except psutil.NoSuchProcess:
            if log_output:
                log(f" [!] Failed to kill Roblox process: PID {self._pid} does not exist", ANSI.RED)
        finally:
            self._pid = None
