from src.constants import (
    EXCLUDE_FULL_GAMES,
    FIRSTLY_SMALL_SERVERS,
    JOIN_TO_FRIENDS,
    LIMIT_SERVERS_PER_PAGE,
    PLACE_ID,
)
from src.ansi import ANSI
from src.enums import JoinToFriends
from src.http import HttpClient
from src.utils import log


async def get_user_info(client: HttpClient) -> tuple[int | None, str | None, str | None]:
    try:
        response = await client.get(
            "https://users.roblox.com/v1/users/authenticated",
        )
        user = response.json()
        user_id = user["id"]
        name = user["name"]
        display_name = user["displayName"]
        return user_id, name, display_name
    except Exception as e:
        log(f"Failed to get User Info ({type(e).__name__}): {e!r}", ANSI.RED)
        return None, None, None


async def get_user_by_username(
    client: HttpClient,
    username: str,
) -> tuple[int | None, str | None, str | None]:
    try:
        response = await client.post(
            "https://users.roblox.com/v1/usernames/users",
            json={
                "usernames": [username],
                "excludeBannedUsers": False,
            },
        )
        users = response.json().get("data", [])
        if not users:
            return None, None, None

        user = users[0]
        user_id = user["id"]
        name = user["name"]
        display_name = user["displayName"]
        return user_id, name, display_name
    except Exception as e:
        log(f" [!] Failed to get User Info By Username ({type(e).__name__}): {e!r}", ANSI.RED)
        return None, None, None


async def get_place_id_user_in(
    client: HttpClient,
    *,
    user_id: int | None = None,
) -> int | None:
    if user_id is None:
        user_id, _, _ = await get_user_info(client)

    if user_id is None:
        log(" [!] Failed to get Place ID: user_id is None", ANSI.RED)
        return None

    try:
        response = await client.post(
            "https://presence.roblox.com/v1/presence/users",
            json={
                "userIds": [user_id]
            },
        )
        place_id = response.json()["userPresences"][0]["placeId"]
        return place_id
    except Exception as e:
        log(f" [!] Failed to get Place ID ({type(e).__name__}): {e!r}", ANSI.RED)
        return None


async def get_x_csrf_token(client: HttpClient) -> str | None:
    try:
        response = await client.post(
            "https://auth.roblox.com/v2/logout",
            allowed_statuses={200, 403},
        )
        x_csrf_token = response.header("x-csrf-token")
        if not x_csrf_token:
            raise KeyError("x-csrf-token")
        log(f" [+] Successfully got X-CSRF-Token", ANSI.CYAN)
        return x_csrf_token
    except Exception as e:
        log(f" [!] Failed to get X-CSRF-Token ({type(e).__name__}): {e!r}", ANSI.RED)
        return None


async def get_auth_ticket(
    client: HttpClient,
    *,
    x_csrf_token: str | None = None,
) -> str | None:
    if x_csrf_token is None:
        x_csrf_token = await get_x_csrf_token(client)

    if not x_csrf_token:
        log(" [!] Failed to get Authentication Ticket: X-CSRF-Token is missing", ANSI.RED)
        return None

    headers = {
        "referer": "https://www.roblox.com/hewhewhew",
        "X-CSRF-Token": x_csrf_token,
    }

    try:
        response = await client.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
            allowed_statuses={200},
        )
        ticket = response.header("rbx-authentication-ticket")
        if not ticket:
            raise KeyError("rbx-authentication-ticket")
        log(f" [+] Successfully got Authentication Ticket", ANSI.CYAN)
        return ticket
    except Exception as e:
        log(f" [!] Failed to get Authentication Ticket ({type(e).__name__}): {e!r}", ANSI.RED)
        return None


async def get_job_id(client: HttpClient) -> str | None:
    try:
        server_types = [0]
        if JOIN_TO_FRIENDS == JoinToFriends.IF_AVAILABLE:
            server_types = [1, 0]

        servers = []
        for index, server_type in enumerate(server_types):
            match index:
                case 0 if server_type == 1:
                    log(" [?] Searching for servers with friends...")
                case _:
                    log(" [?] Searching for any servers...")

            response = (await client.get(
                f"https://games.roblox.com/v1/games/{PLACE_ID}/servers/{server_type}",
                params={
                    "sortOrder": int(FIRSTLY_SMALL_SERVERS),
                    "excludeFullGames": str(EXCLUDE_FULL_GAMES).lower(),
                    "limit": LIMIT_SERVERS_PER_PAGE,
                },
            )).json()
            
            servers = response.get("data", [])
            if servers:
                break

        if not servers:
            log(" [!] Failed to get Job ID: server list is empty", ANSI.RED)
            return None

        job_id = servers[0]["id"]
        log(f" [+] Job ID: {job_id}", ANSI.CYAN)
        return job_id
    except Exception as e:
        log(f" [!] Failed to get Job ID ({type(e).__name__}): {e!r}", ANSI.RED)
        return None
