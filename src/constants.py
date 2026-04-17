from src.enums import JoinToFriends
from src.ansi import ANSI
from src.paths import detect_roblox_path
from src.utils import log


# process
PROCESS_NAME = 'robloxplayerbeta'
RECHECK_CHILD_PROCESSES_INTERVAL = 0.1

# roblox
PATH_ROBLOX = detect_roblox_path()

PLACE_IDS = {
    "Slime RNG": 92416421522960
}
PLACE_NAME = "Slime RNG"
PLACE_ID = PLACE_IDS.get(PLACE_NAME)

FIRSTLY_SMALL_SERVERS = True
EXCLUDE_FULL_GAMES = True
JOIN_TO_FRIENDS = JoinToFriends.IF_AVAILABLE
LIMIT_SERVERS_PER_PAGE = 10

RECHECK_PLAYER_IN_PLACE_INTERVAL = 10
RECHECK_AFTER_LAUNCH_INTERVAL = 60

# http
REQUEST_MAX_TRIES = 5
REQUEST_TIMEOUT = 20
REQUEST_SSL = False
SLEEP_BETWEEN_REQUESTS = 5
ALLOW_REDIRECTS = False
