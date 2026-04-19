import os
from pathlib import Path
from src.regex import ROBLOX_VERSION_PATTERN
from src.utils import log
from src.ansi import ANSI


# system
PATH_TO_LOCALAPPDATA = Path(os.environ['LOCALAPPDATA'])
SYSTEM_DRIVE = Path(os.environ['SystemDrive'])

# roblox
PATH_FISHSTRAP = PATH_TO_LOCALAPPDATA / 'Fishstrap' / 'Fishstrap.exe'
PATH_BLOXSTRAP = PATH_TO_LOCALAPPDATA / 'Bloxstrap' / 'Bloxstrap.exe'

PATHS_ROBLOXPLAYERBETA = [
    SYSTEM_DRIVE / 'Program Files (x86)' / 'Roblox' / 'Versions',
    PATH_TO_LOCALAPPDATA / 'Roblox' / 'Versions',
]
PATH_ROBLOXPLAYERBETA = SYSTEM_DRIVE / 'Program Files (x86)' / 'Roblox' / 'Versions'


def detect_roblox_path() -> Path | None:
    if PATH_FISHSTRAP.exists(): return PATH_FISHSTRAP
    if PATH_BLOXSTRAP.exists(): return PATH_BLOXSTRAP

    for roblox_path in PATHS_ROBLOXPLAYERBETA:
        if not roblox_path.exists():
            continue
        
        paths = sorted(
            list(roblox_path.iterdir()),
            key=lambda e: e.stat().st_mtime,
            reverse=True
        )
        for path in paths:
            if ROBLOX_VERSION_PATTERN.search(str(path)):
                return path
