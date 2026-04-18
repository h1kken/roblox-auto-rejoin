import os
import json
import ctypes
import asyncio
import traceback
from pathlib import Path

import hikari
import lightbulb
import psutil
from dotenv import load_dotenv

from src.ansi import ANSI
from src.constants import (
    PLACE_ID,
    PLACE_NAME,
    PROCESS_NAME,
    RECHECK_AFTER_LAUNCH_INTERVAL,
    RECHECK_PLAYER_IN_PLACE_INTERVAL,
)
from src.http import HttpClient
from src.process import RobloxLauncher
from src.roblox import (
    get_place_id_user_in,
    get_place_name,
    get_user_by_username,
    get_user_info,
)
from src.utils import log

load_dotenv()

STATE_PATH = Path(__file__).with_name("bot_state.json")
BOT_LOOP: asyncio.AbstractEventLoop | None = None
CONSOLE_HANDLER = None
AUTOCHECK_TASKS: dict[int, asyncio.Task] = {}
FARM_TASKS: dict[int, asyncio.Task] = {}
DEFAULT_CHECK_INTERVAL = 10
DEFAULT_FARM_LIMIT = 5
DEFAULT_CHECK_LIMIT = 30


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "default_nicks": {},
            "cookies": {},
            "places": {},
            "muted_notifications": {},
            "force_rejoin": {},
            "whitelist": [],
            "check_interval": DEFAULT_CHECK_INTERVAL,
            "check_limit": DEFAULT_CHECK_LIMIT,
            "farm_limit": DEFAULT_FARM_LIMIT,
            "autochecks": {},
            "farms": {},
        }

    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "default_nicks": {},
            "cookies": {},
            "places": {},
            "muted_notifications": {},
            "force_rejoin": {},
            "whitelist": [],
            "check_interval": DEFAULT_CHECK_INTERVAL,
            "check_limit": DEFAULT_CHECK_LIMIT,
            "farm_limit": DEFAULT_FARM_LIMIT,
            "autochecks": {},
            "farms": {},
        }

    return {
        "default_nicks": data.get("default_nicks", {}),
        "cookies": data.get("cookies", {}),
        "places": data.get("places", {}),
        "muted_notifications": data.get("muted_notifications", {}),
        "force_rejoin": data.get("force_rejoin", {}),
        "whitelist": data.get("whitelist", []),
        "check_interval": int(data.get("check_interval", DEFAULT_CHECK_INTERVAL)),
        "check_limit": int(data.get("check_limit", DEFAULT_CHECK_LIMIT)),
        "farm_limit": int(data.get("farm_limit", DEFAULT_FARM_LIMIT)),
        "autochecks": data.get("autochecks", {}),
        "farms": data.get("farms", {}),
    }


def save_state(data: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def get_default_nick(discord_user_id: int) -> str | None:
    state = load_state()
    return state["default_nicks"].get(str(discord_user_id))


def set_default_nick(discord_user_id: int, nick: str) -> None:
    state = load_state()
    state["default_nicks"][str(discord_user_id)] = nick
    save_state(state)


def get_user_cookie(discord_user_id: int) -> str | None:
    state = load_state()
    return state["cookies"].get(str(discord_user_id))


def set_user_cookie(discord_user_id: int, cookie: str) -> None:
    state = load_state()
    state["cookies"][str(discord_user_id)] = cookie
    save_state(state)


def get_user_place(discord_user_id: int) -> tuple[int, str]:
    state = load_state()
    entry = state["places"].get(str(discord_user_id), {})
    place_id = entry.get("place_id")
    place_name = entry.get("place_name")
    if isinstance(place_id, int) and isinstance(place_name, str) and place_name.strip():
        return place_id, place_name

    return PLACE_ID, PLACE_NAME


def set_user_place(discord_user_id: int, place_id: int, place_name: str) -> None:
    state = load_state()
    state["places"][str(discord_user_id)] = {
        "place_id": place_id,
        "place_name": place_name,
    }
    save_state(state)


def get_muted_notifications(discord_user_id: int) -> bool:
    state = load_state()
    return bool(state["muted_notifications"].get(str(discord_user_id), False))


def set_muted_notifications(discord_user_id: int, value: bool) -> None:
    state = load_state()
    state["muted_notifications"][str(discord_user_id)] = value
    save_state(state)


def get_force_rejoin(discord_user_id: int) -> bool:
    state = load_state()
    return bool(state["force_rejoin"].get(str(discord_user_id), True))


def set_force_rejoin(discord_user_id: int, value: bool) -> None:
    state = load_state()
    state["force_rejoin"][str(discord_user_id)] = value
    save_state(state)


def get_whitelist() -> set[str]:
    state = load_state()
    return {str(user_id) for user_id in state.get("whitelist", [])}


def is_whitelisted(discord_user_id: int) -> bool:
    return is_owner(discord_user_id) or str(discord_user_id) in get_whitelist()


def add_whitelist_user(discord_user_id: int) -> None:
    state = load_state()
    whitelist = {str(user_id) for user_id in state.get("whitelist", [])}
    whitelist.add(str(discord_user_id))
    state["whitelist"] = sorted(whitelist, key=int)
    save_state(state)


def remove_whitelist_user(discord_user_id: int) -> None:
    state = load_state()
    whitelist = {str(user_id) for user_id in state.get("whitelist", [])}
    whitelist.discard(str(discord_user_id))
    state["whitelist"] = sorted(whitelist, key=int)
    save_state(state)


def get_check_interval() -> int:
    return load_state()["check_interval"]


def set_check_interval(seconds: int) -> None:
    state = load_state()
    state["check_interval"] = seconds
    save_state(state)


def get_check_limit() -> int:
    return load_state()["check_limit"]


def set_check_limit(limit: int) -> None:
    state = load_state()
    state["check_limit"] = limit
    save_state(state)


def get_farm_limit() -> int:
    return load_state()["farm_limit"]


def set_farm_limit(limit: int) -> None:
    state = load_state()
    state["farm_limit"] = limit
    save_state(state)


def get_autochecks() -> dict[str, dict]:
    return load_state()["autochecks"]


def set_autocheck(
    discord_user_id: int,
    *,
    nick: str,
    user_id: int,
    username: str,
    last_status: bool,
) -> None:
    state = load_state()
    state["autochecks"][str(discord_user_id)] = {
        "nick": nick,
        "user_id": user_id,
        "username": username,
        "last_status": last_status,
    }
    save_state(state)


def update_autocheck_last_status(discord_user_id: int, last_status: bool) -> None:
    state = load_state()
    entry = state["autochecks"].get(str(discord_user_id))
    if entry is None:
        return

    entry["last_status"] = last_status
    save_state(state)


def remove_autocheck(discord_user_id: int) -> None:
    state = load_state()
    state["autochecks"].pop(str(discord_user_id), None)
    save_state(state)


def get_farms() -> dict[str, dict]:
    return load_state()["farms"]


def is_autofarm_enabled(discord_user_id: int) -> bool:
    return str(discord_user_id) in get_farms()


def set_farm(
    discord_user_id: int,
    *,
    user_id: int,
    username: str,
    process_pid: int | None = None,
    process_name: str | None = None,
) -> None:
    state = load_state()
    state["farms"][str(discord_user_id)] = {
        "user_id": user_id,
        "username": username,
        "process_pid": process_pid,
        "process_name": process_name,
    }
    save_state(state)


def update_farm_process(
    discord_user_id: int,
    *,
    process_pid: int | None,
    process_name: str | None,
) -> None:
    state = load_state()
    entry = state["farms"].get(str(discord_user_id))
    if entry is None:
        return

    entry["process_pid"] = process_pid
    entry["process_name"] = process_name
    save_state(state)


def get_farm_process_pid(discord_user_id: int) -> int | None:
    entry = get_farms().get(str(discord_user_id), {})
    process_pid = entry.get("process_pid")
    if isinstance(process_pid, int):
        return process_pid

    return None


def remove_farm(discord_user_id: int) -> None:
    state = load_state()
    state["farms"].pop(str(discord_user_id), None)
    save_state(state)


def parse_default_guilds() -> list[hikari.Snowflake]:
    raw = os.getenv("DISCORD_GUILD_IDS") or os.getenv("DISCORD_GUILD_ID")
    if not raw:
        return []

    guild_ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        guild_ids.append(hikari.Snowflake(part))
    return guild_ids


def is_owner(discord_user_id: int) -> bool:
    owner_id = os.getenv("DISCORD_OWNER_ID")
    return bool(owner_id) and str(discord_user_id) == owner_id


def format_place(place_id: int, place_name: str) -> str:
    return f"{place_name} ({place_id})"


def bot_console_log(message: str, color: str = ANSI.WHITE) -> None:
    log(message, color)


def get_message_flags(discord_user_id: int) -> hikari.MessageFlag | hikari.UndefinedType:
    if get_muted_notifications(discord_user_id):
        return hikari.MessageFlag.SUPPRESS_NOTIFICATIONS

    return hikari.UNDEFINED


async def resolve_player(username: str, cookie: str) -> tuple[int | None, str | None]:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        user_id, actual_name, _ = await get_user_by_username(client, username)
        return user_id, actual_name


async def get_authenticated_user(cookie: str) -> tuple[int | None, str | None]:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        user_id, actual_name, _ = await get_user_info(client)
        return user_id, actual_name


async def resolve_place(place_id: int) -> str:
    async with HttpClient() as client:
        return (await get_place_name(client, place_id)) or f"Place {place_id}"


async def check_player_status(
    username: str,
    cookie: str,
    target_place_id: int,
) -> tuple[bool | None, str | None]:
    user_id, actual_name = await resolve_player(username, cookie)
    if user_id is None:
        return None, None

    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        place_id = await get_place_id_user_in(client, user_id=user_id)
        return place_id == target_place_id, actual_name


async def check_player_status_by_id(user_id: int, cookie: str, target_place_id: int) -> bool:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        place_id = await get_place_id_user_in(client, user_id=user_id)
        return place_id == target_place_id


async def autocheck_loop(
    bot: hikari.GatewayBot,
    discord_user_id: int,
    user_id: int,
    username: str,
    cookie: str,
    *,
    last_status: bool | None = None,
) -> None:
    if last_status is None:
        target_place_id, _ = get_user_place(discord_user_id)
        last_status = await check_player_status_by_id(user_id, cookie, target_place_id)

    dm_channel = await bot.rest.create_dm_channel(discord_user_id)

    try:
        while True:
            await asyncio.sleep(get_check_interval())
            target_place_id, target_place_name = get_user_place(discord_user_id)
            current_status = await check_player_status_by_id(user_id, cookie, target_place_id)
            if current_status == last_status:
                continue

            if is_autofarm_enabled(discord_user_id):
                last_status = current_status
                update_autocheck_last_status(discord_user_id, last_status)
                continue

            if current_status:
                bot_console_log(
                    f"✅ AutoCheck | is in {format_place(target_place_id, target_place_name)}",
                    ANSI.GREEN,
                )
                await bot.rest.create_message(
                    dm_channel.id,
                    f"✅ AutoCheck | is in {format_place(target_place_id, target_place_name)}",
                    flags=get_message_flags(discord_user_id),
                )
            else:
                bot_console_log(
                    f"❌ AutoCheck | is not in {format_place(target_place_id, target_place_name)}",
                    ANSI.RED,
                )
                await bot.rest.create_message(
                    dm_channel.id,
                    f"❌ AutoCheck | is not in {format_place(target_place_id, target_place_name)}",
                    flags=get_message_flags(discord_user_id),
                )

            last_status = current_status
            update_autocheck_last_status(discord_user_id, last_status)
    except asyncio.CancelledError:
        raise
    finally:
        AUTOCHECK_TASKS.pop(discord_user_id, None)


async def farm_loop(
    bot: hikari.GatewayBot,
    discord_user_id: int,
    cookie: str,
    user_id: int,
    username: str,
    *,
    process_pid: int | None = None,
    suppress_initial_notification: bool = False,
) -> None:
    launcher = RobloxLauncher(process_pid if isinstance(process_pid, int) and psutil.pid_exists(process_pid) else None)
    cookies = {".ROBLOSECURITY": cookie}
    current_task = asyncio.current_task()
    last_action: str | None = None
    dm_channel = await bot.rest.create_dm_channel(discord_user_id)
    skip_next_notification = suppress_initial_notification

    try:
        async with HttpClient(cookies=cookies) as client:
            while True:
                try:
                    target_place_id, target_place_name = get_user_place(discord_user_id)
                    place_id = await get_place_id_user_in(client, user_id=user_id)
                    if place_id == target_place_id:
                        action_key = f"in:{target_place_id}"
                        if last_action != action_key:
                            if not skip_next_notification:
                                bot_console_log(
                                    f"✅ AutoFarm | `{username}` is in {format_place(target_place_id, target_place_name)}",
                                    ANSI.GREEN,
                                )
                                await bot.rest.create_message(
                                    dm_channel.id,
                                    f"✅ AutoFarm | `{username}` is in {format_place(target_place_id, target_place_name)}",
                                    flags=get_message_flags(discord_user_id),
                                )
                            last_action = action_key
                            skip_next_notification = False
                        await asyncio.sleep(RECHECK_PLAYER_IN_PLACE_INTERVAL)
                        continue

                    if place_id is not None and not get_force_rejoin(discord_user_id):
                        action_key = f"other:{place_id}"
                        if last_action != action_key:
                            if not skip_next_notification:
                                bot_console_log(
                                    f"⏸️ AutoFarm | `{username}` is in another place ({place_id})",
                                    ANSI.YELLOW,
                                )
                                await bot.rest.create_message(
                                    dm_channel.id,
                                    f"⏸️ AutoFarm | `{username}` is in another place ({place_id}). Force rejoin is off.",
                                    flags=get_message_flags(discord_user_id),
                                )
                            last_action = action_key
                            skip_next_notification = False
                        await asyncio.sleep(RECHECK_PLAYER_IN_PLACE_INTERVAL)
                        continue

                    action_key = f"joining:{target_place_id}"
                    if last_action != action_key:
                        if not skip_next_notification:
                            bot_console_log(
                                f"🔄 AutoFarm | `{username}` joining to {format_place(target_place_id, target_place_name)}",
                                ANSI.YELLOW,
                            )
                            await bot.rest.create_message(
                                dm_channel.id,
                                f"🔄 AutoFarm | `{username}` joining to {format_place(target_place_id, target_place_name)}",
                                flags=get_message_flags(discord_user_id),
                            )
                        last_action = action_key
                        skip_next_notification = False

                    await launcher.launch(client, place_id=target_place_id, log_output=False)
                    update_farm_process(
                        discord_user_id,
                        process_pid=launcher.pid,
                        process_name=launcher.process_name if launcher.pid is not None else None,
                    )
                    await asyncio.sleep(RECHECK_AFTER_LAUNCH_INTERVAL)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    traceback.print_exc()
                    await asyncio.sleep(RECHECK_AFTER_LAUNCH_INTERVAL)
    finally:
        if FARM_TASKS.get(discord_user_id) is current_task:
            FARM_TASKS.pop(discord_user_id, None)


async def start_autocheck(
    bot: hikari.GatewayBot,
    discord_user_id: int,
    nick: str,
    cookie: str,
    *,
    send_enabled_message: bool = True,
) -> None:
    try:
        user_id, actual_name = await resolve_player(nick, cookie)
        dm_channel = await bot.rest.create_dm_channel(discord_user_id)
        target_place_id, target_place_name = get_user_place(discord_user_id)

        if user_id is None:
            await bot.rest.create_message(
                dm_channel.id,
                f"❌ AutoCheck | User `{nick}` not found. Auto-check was not enabled.",
                flags=get_message_flags(discord_user_id),
            )
            return

        username = actual_name or nick
        current_status = await check_player_status_by_id(user_id, cookie, target_place_id)

        set_autocheck(
            discord_user_id,
            nick=nick,
            user_id=user_id,
            username=username,
            last_status=current_status,
        )

        task = asyncio.create_task(
            autocheck_loop(
                bot,
                discord_user_id,
                user_id,
                username,
                cookie,
                last_status=current_status,
            )
        )
        AUTOCHECK_TASKS[discord_user_id] = task
        if send_enabled_message and not is_autofarm_enabled(discord_user_id):
            await bot.rest.create_message(
                dm_channel.id,
                f"✅ AutoCheck | Enabled for `{username}` in {format_place(target_place_id, target_place_name)}",
                flags=get_message_flags(discord_user_id),
            )
            status_text = "is in" if current_status else "is not in"
            await bot.rest.create_message(
                dm_channel.id,
                f"{'✅' if current_status else '❌'} AutoCheck | {status_text} {format_place(target_place_id, target_place_name)}",
                flags=get_message_flags(discord_user_id),
            )
    except Exception:
        traceback.print_exc()


async def safe_respond(
    ctx: lightbulb.Context,
    content: str,
    *,
    ephemeral: bool = False,
) -> bool:
    try:
        await ctx.respond(content, ephemeral=ephemeral)
        return True
    except hikari.NotFoundError:
        return False


async def safe_defer(
    ctx: lightbulb.Context,
    *,
    ephemeral: bool = False,
) -> bool:
    try:
        await ctx.defer(ephemeral=ephemeral)
        return True
    except hikari.NotFoundError:
        return False


async def send_command_message(
    bot: hikari.GatewayBot,
    ctx: lightbulb.Context,
    content: str,
    *,
    ephemeral: bool = False,
) -> None:
    responded = await safe_respond(ctx, content, ephemeral=ephemeral)
    if responded:
        return

    if ephemeral:
        return

    channel_id = getattr(ctx, "channel_id", None)
    if channel_id is None:
        return

    try:
        await bot.rest.create_message(
            channel_id,
            content,
            flags=get_message_flags(ctx.user.id),
        )
    except Exception:
        traceback.print_exc()


async def ensure_whitelisted(ctx: lightbulb.Context) -> bool:
    if is_whitelisted(ctx.user.id):
        return True

    await safe_respond(ctx, "🔒 You are not whitelisted.", ephemeral=True)
    return False


async def restore_autochecks(bot: hikari.GatewayBot, cookie: str) -> None:
    for discord_user_id_raw, entry in get_autochecks().items():
        discord_user_id = int(discord_user_id_raw)
        if discord_user_id in AUTOCHECK_TASKS:
            continue

        user_id = entry.get("user_id")
        username = entry.get("username")
        nick = entry.get("nick")
        last_status = entry.get("last_status")

        if not isinstance(user_id, int) or not isinstance(username, str) or not isinstance(nick, str):
            continue

        AUTOCHECK_TASKS[discord_user_id] = asyncio.create_task(
            autocheck_loop(
                bot,
                discord_user_id,
                user_id,
                username,
                cookie,
                last_status=bool(last_status),
            )
        )


async def restore_farms(bot: hikari.GatewayBot) -> None:
    for discord_user_id_raw, entry in get_farms().items():
        discord_user_id = int(discord_user_id_raw)
        if discord_user_id in FARM_TASKS:
            continue

        cookie = get_user_cookie(discord_user_id)
        if not isinstance(cookie, str) or not cookie:
            remove_farm(discord_user_id)
            continue

        user_id = entry.get("user_id")
        username = entry.get("username")
        process_pid = entry.get("process_pid")
        if not isinstance(user_id, int) or not isinstance(username, str):
            remove_farm(discord_user_id)
            continue

        FARM_TASKS[discord_user_id] = asyncio.create_task(
            farm_loop(
                bot,
                discord_user_id,
                cookie,
                user_id,
                username,
                process_pid=process_pid if isinstance(process_pid, int) else None,
                suppress_initial_notification=True,
            )
        )


def build_bot() -> hikari.GatewayBot:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")

    roblox_cookie = os.getenv("ROBLOX_COOKIE")
    if not roblox_cookie:
        raise RuntimeError("ROBLOX_COOKIE is not set")

    bot = hikari.GatewayBot(token=token)
    client = lightbulb.client_from_app(bot)

    @bot.listen(hikari.StartingEvent)
    async def on_starting(_event: hikari.StartingEvent) -> None:
        global BOT_LOOP
        BOT_LOOP = asyncio.get_running_loop()
        asyncio.create_task(restore_autochecks(bot, roblox_cookie))
        asyncio.create_task(restore_farms(bot))

    @bot.listen(hikari.StoppingEvent)
    async def on_stopping(_event: hikari.StoppingEvent) -> None:
        for task in tuple(AUTOCHECK_TASKS.values()):
            task.cancel()
        for task in tuple(FARM_TASKS.values()):
            task.cancel()

    @client.error_handler(priority=100)
    async def on_command_error(exception: lightbulb.exceptions.ExecutionPipelineFailedException) -> bool:
        cause = exception.invocation_failure or exception.__cause__ or exception
        traceback.print_exception(type(cause), cause, cause.__traceback__)

        try:
            await exception.context.respond("An internal error occurred.", ephemeral=True)
        except Exception:
            pass

        return True

    @client.register()
    class Ping(
        lightbulb.SlashCommand,
        name="ping",
        description="Shows bot latency",
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer()
            latency_ms = int((bot.heartbeat_latency or 0) * 1000)
            await ctx.respond(f"🏓 Pong!\n```Latency: {latency_ms}ms```")

    @client.register()
    class SetNick(
        lightbulb.SlashCommand,
        name="setnick",
        description="Sets default nick for /check",
    ):
        nick = lightbulb.string("nick", "Roblox nickname")

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            nick = self.nick.strip()
            if not nick:
                await ctx.respond("Nick cannot be empty.", ephemeral=True)
                return

            set_default_nick(ctx.user.id, nick)
            await ctx.respond(f"✨ Default nick set to `{nick}`.", ephemeral=True)

    @client.register()
    class SetCookie(
        lightbulb.SlashCommand,
        name="setcookie",
        description="Sets cookie used for farming",
    ):
        cookie = lightbulb.string("cookie", "ROBLOSECURITY cookie")

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            cookie = self.cookie.strip()
            if not cookie:
                await ctx.respond("Cookie cannot be empty.", ephemeral=True)
                return

            set_user_cookie(ctx.user.id, cookie)
            await ctx.respond("🍪 Cookie saved.", ephemeral=True)

    @client.register()
    class SetPlace(
        lightbulb.SlashCommand,
        name="setplace",
        description="Sets target place used by /check, /autocheck and /autofarm",
    ):
        place_id = lightbulb.integer(
            "id",
            "Roblox place id",
            min_value=1,
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            place_name = await resolve_place(self.place_id)
            set_user_place(ctx.user.id, self.place_id, place_name)
            await ctx.respond(
                f"🗺️ Target place set to {format_place(self.place_id, place_name)}.",
                ephemeral=True,
            )

    @client.register()
    class Nick(
        lightbulb.SlashCommand,
        name="nick",
        description="Shows current nick used by /check",
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            nick = get_default_nick(ctx.user.id)
            if not nick:
                await ctx.respond("Nick is not set. Use `/setnick` first.", ephemeral=True)
                return

            await ctx.respond(f"✨ Current nick: `{nick}`", ephemeral=True)

    @client.register()
    class MutedNotifications(
        lightbulb.SlashCommand,
        name="mutednotifications",
        description="Turns quiet bot notifications on or off",
    ):
        state = lightbulb.string(
            "state",
            "Muted notifications state",
            choices=[
                lightbulb.Choice("on", "on"),
                lightbulb.Choice("off", "off"),
            ],
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await safe_defer(ctx, ephemeral=True)
            enabled = self.state.lower().strip() == "on"
            set_muted_notifications(ctx.user.id, enabled)
            await safe_respond(
                ctx,
                f"{'🔕' if enabled else '🔔'} Muted notifications {'enabled' if enabled else 'disabled'}.",
                ephemeral=True,
            )

    @client.register()
    class ForceRejoin(
        lightbulb.SlashCommand,
        name="forcerejoin",
        description="Controls whether auto-farm should force join the target place",
    ):
        state = lightbulb.string(
            "state",
            "Ignore being in another place and force join target place under auto-farm",
            choices=[
                lightbulb.Choice("on", "on"),
                lightbulb.Choice("off", "off"),
            ],
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await safe_defer(ctx, ephemeral=True)
            enabled = self.state.lower().strip() == "on"
            set_force_rejoin(ctx.user.id, enabled)
            await safe_respond(
                ctx,
                f"{'🔄' if enabled else '⏸️'} Force rejoin {'enabled' if enabled else 'disabled'}.",
                ephemeral=True,
            )

    @client.register()
    class Whitelist(
        lightbulb.SlashCommand,
        name="whitelist",
        description="Adds or removes a user from the bot whitelist",
    ):
        action = lightbulb.string(
            "action",
            "Whitelist action",
            choices=[
                lightbulb.Choice("add", "add"),
                lightbulb.Choice("remove", "remove"),
            ],
        )
        user = lightbulb.user("user", "Discord user")

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await safe_defer(ctx, ephemeral=True)
            if not is_owner(ctx.user.id):
                await safe_respond(ctx, "🔒 Owner only.", ephemeral=True)
                return

            action = self.action.lower().strip()
            target = self.user
            if action == "add":
                add_whitelist_user(target.id)
                try:
                    dm_channel = await bot.rest.create_dm_channel(target.id)
                    await bot.rest.create_message(
                        dm_channel.id,
                        "✅ Whitelist | You have been added to the bot whitelist.",
                    )
                except Exception:
                    traceback.print_exc()
                await safe_respond(ctx, f"✅ Whitelist | Added <@{target.id}>.", ephemeral=True)
                return

            if is_owner(target.id):
                await safe_respond(ctx, "🔒 Whitelist | Owner cannot be removed.", ephemeral=True)
                return

            remove_whitelist_user(target.id)
            await safe_respond(ctx, f"❌ Whitelist | Removed <@{target.id}>.", ephemeral=True)

    @client.register()
    class Check(
        lightbulb.SlashCommand,
        name="check",
        description="Checks if a player is in the configured place",
    ):
        nick = lightbulb.string(
            "nick",
            "Roblox nickname",
            default=None,
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            try:
                if not await ensure_whitelisted(ctx):
                    return
                raw_nick = self.nick if isinstance(self.nick, str) else None
                nick = (raw_nick or get_default_nick(ctx.user.id) or "").strip()
                if not nick:
                    await send_command_message(
                        bot,
                        ctx,
                        "Nick is not set. Use `/setnick` or pass `nick` in `/check`.",
                        ephemeral=True,
                    )
                    return

                await safe_defer(ctx)
                target_place_id, target_place_name = get_user_place(ctx.user.id)

                status, actual_name = await check_player_status(nick, roblox_cookie, target_place_id)
                if status is None:
                    await send_command_message(bot, ctx, f"❌ User `{nick}` not found.")
                    return

                shown_name = actual_name or nick
                if status:
                    await send_command_message(
                        bot,
                        ctx,
                        f"`{shown_name}` | ✅ is in {format_place(target_place_id, target_place_name)}",
                    )
                    return

                await send_command_message(
                    bot,
                    ctx,
                    f"`{shown_name}` | ❌ is not in {format_place(target_place_id, target_place_name)}",
                )
            except Exception:
                traceback.print_exc()
                raise

    @client.register()
    class AutoCheck(
        lightbulb.SlashCommand,
        name="autocheck",
        description="Turns periodic checking on or off",
    ):
        state = lightbulb.string(
            "state",
            "Auto-check state",
            choices=[
                lightbulb.Choice("on", "on"),
                lightbulb.Choice("off", "off"),
            ],
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            state = self.state.lower().strip()
            if state == "off":
                task = AUTOCHECK_TASKS.pop(ctx.user.id, None)
                remove_autocheck(ctx.user.id)
                if task is None:
                    await safe_respond(ctx, "❌ AutoCheck | Already off.", ephemeral=True)
                    return

                task.cancel()
                await safe_respond(ctx, "❌ AutoCheck | Disabled.", ephemeral=True)
                return

            nick = (get_default_nick(ctx.user.id) or "").strip()
            if not nick:
                await safe_respond(ctx, "❌ AutoCheck | Nick is not set. Use `/setnick` first.", ephemeral=True)
                return

            autochecks = get_autochecks()
            is_restart = str(ctx.user.id) in autochecks
            if not is_restart and len(autochecks) >= get_check_limit():
                await safe_respond(
                    ctx,
                    f"🚫 AutoCheck | Check limit reached. Try again later. Current limit: `{get_check_limit()}`.",
                    ephemeral=True,
                )
                return

            existing = AUTOCHECK_TASKS.pop(ctx.user.id, None)
            if existing is not None:
                existing.cancel()

            await safe_respond(
                ctx,
                f"🔄 AutoCheck | Starting for `{nick}`. Notifications will be sent in DMs.",
                ephemeral=True,
            )

            asyncio.create_task(
                start_autocheck(
                    bot,
                    ctx.user.id,
                    nick,
                    roblox_cookie,
                    send_enabled_message=True,
                )
            )

    @client.register()
    class AutoFarm(
        lightbulb.SlashCommand,
        name="autofarm",
        description="Turns local farming on or off",
    ):
        state = lightbulb.string(
            "state",
            "Auto-farm state",
            choices=[
                lightbulb.Choice("on", "on"),
                lightbulb.Choice("off", "off"),
            ],
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            if not await safe_defer(ctx, ephemeral=True):
                return

            state = self.state.lower().strip()
            if state == "off":
                task = FARM_TASKS.pop(ctx.user.id, None)
                process_pid = get_farm_process_pid(ctx.user.id)
                remove_farm(ctx.user.id)
                if task is None:
                    if process_pid is not None:
                        RobloxLauncher(process_pid).kill(log_output=False)
                    await safe_respond(ctx, "❌ AutoFarm | Already off.", ephemeral=True)
                    return

                task.cancel()
                if process_pid is not None:
                    RobloxLauncher(process_pid).kill(log_output=False)
                await safe_respond(ctx, "❌ AutoFarm | Disabled.", ephemeral=True)
                return

            cookie = (get_user_cookie(ctx.user.id) or "").strip()
            if not cookie:
                await safe_respond(ctx, "❌ AutoFarm | Cookie is not set. Use `/setcookie` first.", ephemeral=True)
                return

            farms = get_farms()
            is_restart = str(ctx.user.id) in farms
            if not is_restart and len(farms) >= get_farm_limit():
                await safe_respond(
                    ctx,
                    f"🚫 AutoFarm | Farm limit reached. Try again later. Current limit: `{get_farm_limit()}`.",
                    ephemeral=True,
                )
                return

            user_id, username = await get_authenticated_user(cookie)
            if user_id is None or username is None:
                await safe_respond(ctx, "❌ AutoFarm | Failed to validate cookie.", ephemeral=True)
                return

            existing = FARM_TASKS.pop(ctx.user.id, None)
            existing_process_pid = get_farm_process_pid(ctx.user.id)
            if existing is not None:
                existing.cancel()
            if existing_process_pid is not None:
                RobloxLauncher(existing_process_pid).kill(log_output=False)

            set_farm(
                ctx.user.id,
                user_id=user_id,
                username=username,
                process_pid=None,
                process_name=PROCESS_NAME,
            )

            FARM_TASKS[ctx.user.id] = asyncio.create_task(
                farm_loop(
                    bot,
                    ctx.user.id,
                    cookie,
                    user_id,
                    username,
                    process_pid=existing_process_pid,
                )
            )

            target_place_id, target_place_name = get_user_place(ctx.user.id)
            await safe_respond(
                ctx,
                f"✅ AutoFarm | Enabled for `{username}` in {format_place(target_place_id, target_place_name)}. Active farms: `{len(get_farms())}/{get_farm_limit()}`.",
                ephemeral=True,
            )

    @client.register()
    class CheckInterval(
        lightbulb.SlashCommand,
        name="checkinterval",
        description="Changes auto-check interval in seconds",
    ):
        seconds = lightbulb.integer(
            "seconds",
            "Interval in seconds",
            min_value=1,
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            if not is_owner(ctx.user.id):
                await ctx.respond("🔒 Owner only.", ephemeral=True)
                return

            set_check_interval(self.seconds)
            await ctx.respond(f"⏱️ Check interval set to `{self.seconds}` seconds.", ephemeral=True)

    @client.register()
    class SetCheckLimit(
        lightbulb.SlashCommand,
        name="setchecklimit",
        description="Changes global auto-check limit",
    ):
        limit = lightbulb.integer(
            "limit",
            "Global auto-check limit",
            min_value=1,
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            if not is_owner(ctx.user.id):
                await ctx.respond("🔒 Owner only.", ephemeral=True)
                return

            set_check_limit(self.limit)
            await ctx.respond(f"🧮 Check limit set to `{self.limit}`.", ephemeral=True)

    @client.register()
    class SetFarmLimit(
        lightbulb.SlashCommand,
        name="setfarmlimit",
        description="Changes global farm limit",
    ):
        limit = lightbulb.integer(
            "limit",
            "Global farm limit",
            min_value=1,
        )

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            if not await ensure_whitelisted(ctx):
                return
            await ctx.defer(ephemeral=True)
            if not is_owner(ctx.user.id):
                await ctx.respond("🔒 Owner only.", ephemeral=True)
                return

            set_farm_limit(self.limit)
            await ctx.respond(f"🧺 Farm limit set to `{self.limit}`.", ephemeral=True)

    bot.subscribe(hikari.StartingEvent, client.start)
    bot.subscribe(hikari.StoppingEvent, client.stop)
    return bot


def install_console_close_handler(bot: hikari.GatewayBot) -> None:
    global CONSOLE_HANDLER

    if os.name != "nt":
        return

    CTRL_C_EVENT = 0
    CTRL_BREAK_EVENT = 1
    CTRL_CLOSE_EVENT = 2
    CTRL_LOGOFF_EVENT = 5
    CTRL_SHUTDOWN_EVENT = 6

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def handler(event_type: int) -> bool:
        if event_type in {
            CTRL_C_EVENT,
            CTRL_BREAK_EVENT,
            CTRL_CLOSE_EVENT,
            CTRL_LOGOFF_EVENT,
            CTRL_SHUTDOWN_EVENT,
        }:
            try:
                if BOT_LOOP is not None and BOT_LOOP.is_running():
                    future = asyncio.run_coroutine_threadsafe(bot.close(), BOT_LOOP)
                    future.result(timeout=5)
            except Exception:
                pass
            finally:
                os._exit(0)
        return True

    CONSOLE_HANDLER = handler
    ctypes.windll.kernel32.SetConsoleCtrlHandler(CONSOLE_HANDLER, True)


def main() -> None:
    bot = build_bot()
    install_console_close_handler(bot)
    bot.run()


if __name__ == "__main__":
    main()
