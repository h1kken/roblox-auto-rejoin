import asyncio
import ctypes
import json
import os
import traceback
from pathlib import Path

import hikari
import lightbulb
from dotenv import load_dotenv

from src.constants import PLACE_ID
from src.http import HttpClient
from src.roblox import get_place_id_user_in, get_user_by_username

load_dotenv()

STATE_PATH = Path(__file__).with_name("bot_state.json")
BOT_LOOP: asyncio.AbstractEventLoop | None = None
CONSOLE_HANDLER = None
AUTOCHECK_TASKS: dict[int, asyncio.Task] = {}
DEFAULT_CHECK_INTERVAL = 10


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "default_nicks": {},
            "check_interval": DEFAULT_CHECK_INTERVAL,
            "autochecks": {},
        }

    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "default_nicks": {},
            "check_interval": DEFAULT_CHECK_INTERVAL,
            "autochecks": {},
        }

    return {
        "default_nicks": data.get("default_nicks", {}),
        "check_interval": int(data.get("check_interval", DEFAULT_CHECK_INTERVAL)),
        "autochecks": data.get("autochecks", {}),
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


def get_check_interval() -> int:
    return load_state()["check_interval"]


def set_check_interval(seconds: int) -> None:
    state = load_state()
    state["check_interval"] = seconds
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


async def resolve_player(username: str, cookie: str) -> tuple[int | None, str | None]:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        user_id, actual_name, _ = await get_user_by_username(client, username)
        return user_id, actual_name


async def check_player_status(username: str, cookie: str) -> tuple[bool | None, str | None]:
    user_id, actual_name = await resolve_player(username, cookie)
    if user_id is None:
        return None, None

    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        place_id = await get_place_id_user_in(client, user_id=user_id)
        return place_id == PLACE_ID, actual_name


async def check_player_status_by_id(user_id: int, cookie: str) -> bool:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        place_id = await get_place_id_user_in(client, user_id=user_id)
        return place_id == PLACE_ID


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
        last_status = await check_player_status_by_id(user_id, cookie)

    dm_channel = await bot.rest.create_dm_channel(discord_user_id)

    try:
        while True:
            await asyncio.sleep(get_check_interval())
            current_status = await check_player_status_by_id(user_id, cookie)
            if current_status == last_status:
                continue

            if current_status:
                await bot.rest.create_message(
                    dm_channel.id,
                    f"`{username}` | ✅ In Game (id: {PLACE_ID})",
                )
            else:
                await bot.rest.create_message(
                    dm_channel.id,
                    f"`{username}` | ❌ Not In Game (id: {PLACE_ID})",
                )

            last_status = current_status
            update_autocheck_last_status(discord_user_id, last_status)
    except asyncio.CancelledError:
        raise
    finally:
        AUTOCHECK_TASKS.pop(discord_user_id, None)


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

        if user_id is None:
            await bot.rest.create_message(
                dm_channel.id,
                f"❌ User `{nick}` not found. Auto-check was not enabled.",
            )
            return

        username = actual_name or nick
        current_status = await check_player_status_by_id(user_id, cookie)

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


def build_bot() -> hikari.GatewayBot:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")

    roblox_cookie = os.getenv("ROBLOX_COOKIE")
    if not roblox_cookie:
        raise RuntimeError("ROBLOX_COOKIE is not set")

    bot = hikari.GatewayBot(token=token)
    client = lightbulb.client_from_app(
        bot,
        default_enabled_guilds=parse_default_guilds(),
    )

    @bot.listen(hikari.StartingEvent)
    async def on_starting(_event: hikari.StartingEvent) -> None:
        global BOT_LOOP
        BOT_LOOP = asyncio.get_running_loop()
        asyncio.create_task(restore_autochecks(bot, roblox_cookie))

    @bot.listen(hikari.StoppingEvent)
    async def on_stopping(_event: hikari.StoppingEvent) -> None:
        for task in tuple(AUTOCHECK_TASKS.values()):
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
            await ctx.defer(ephemeral=True)
            nick = self.nick.strip()
            if not nick:
                await ctx.respond("Nick cannot be empty.", ephemeral=True)
                return

            set_default_nick(ctx.user.id, nick)
            await ctx.respond(f"Default nick set to `{nick}`.", ephemeral=True)

    @client.register()
    class Nick(
        lightbulb.SlashCommand,
        name="nick",
        description="Shows current nick used by /check",
    ):
        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            await ctx.defer(ephemeral=True)
            nick = get_default_nick(ctx.user.id)
            if not nick:
                await ctx.respond("Nick is not set. Use `/setnick` first.", ephemeral=True)
                return

            await ctx.respond(f"Current nick: `{nick}`", ephemeral=True)

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
                raw_nick = self.nick if isinstance(self.nick, str) else None
                nick = (raw_nick or get_default_nick(ctx.user.id) or "").strip()
                if not nick:
                    await ctx.defer(ephemeral=True)
                    await ctx.respond(
                        "Nick is not set. Use `/setnick` or pass `nick` in `/check`.",
                        ephemeral=True,
                    )
                    return

                await ctx.defer()

                status, actual_name = await check_player_status(nick, roblox_cookie)
                if status is None:
                    await ctx.respond(f"❌ User `{nick}` not found.")
                    return

                shown_name = actual_name or nick
                if status:
                    await ctx.respond(f"`{shown_name}` | ✅ In Game (id: {PLACE_ID})")
                    return

                await ctx.respond(f"`{shown_name}` | ❌ Not In Game (id: {PLACE_ID})")
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
            state = self.state.lower().strip()
            if state == "off":
                task = AUTOCHECK_TASKS.pop(ctx.user.id, None)
                remove_autocheck(ctx.user.id)
                if task is None:
                    await safe_respond(ctx, "Auto-check is already off.", ephemeral=True)
                    return

                task.cancel()
                await safe_respond(ctx, "Auto-check disabled.", ephemeral=True)
                return

            nick = (get_default_nick(ctx.user.id) or "").strip()
            if not nick:
                await safe_respond(ctx, "Nick is not set. Use `/setnick` first.", ephemeral=True)
                return

            existing = AUTOCHECK_TASKS.pop(ctx.user.id, None)
            if existing is not None:
                existing.cancel()

            await safe_respond(
                ctx,
                f"Starting auto-check for `{nick}`. Notifications will be sent in DMs.",
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
            await ctx.defer(ephemeral=True)
            if not is_owner(ctx.user.id):
                await ctx.respond("Owner only.", ephemeral=True)
                return

            set_check_interval(self.seconds)
            await ctx.respond(f"Check interval set to `{self.seconds}` seconds.", ephemeral=True)

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
