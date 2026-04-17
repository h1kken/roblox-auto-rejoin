import asyncio
import json
import os
import traceback
import ctypes
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


def load_default_nicks() -> dict[str, str]:
    if not STATE_PATH.exists():
        return {}

    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_default_nicks(data: dict[str, str]) -> None:
    STATE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def get_default_nick(discord_user_id: int) -> str | None:
    return load_default_nicks().get(str(discord_user_id))


def set_default_nick(discord_user_id: int, nick: str) -> None:
    data = load_default_nicks()
    data[str(discord_user_id)] = nick
    save_default_nicks(data)


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


async def check_player_status(username: str, cookie: str) -> tuple[bool | None, str | None]:
    cookies = {".ROBLOSECURITY": cookie}
    async with HttpClient(cookies=cookies) as client:
        user_id, actual_name, _ = await get_user_by_username(client, username)
        if user_id is None:
            return None, None

        place_id = await get_place_id_user_in(client, user_id=user_id)
        return place_id == PLACE_ID, actual_name


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
            latency_ms = int((bot.heartbeat_latency or 0) * 1000)
            await ctx.respond(f"🏓 Pong!\n```red\nLatency: {latency_ms}ms```")

    @client.register()
    class SetNick(
        lightbulb.SlashCommand,
        name="setnick",
        description="Sets default nick for /check",
    ):
        nick = lightbulb.string("nick", "Roblox nickname")

        @lightbulb.invoke
        async def invoke(self, ctx: lightbulb.Context) -> None:
            nick = self.nick.strip()
            if not nick:
                await ctx.respond("Nick cannot be empty.", ephemeral=True)
                return

            set_default_nick(ctx.user.id, nick)
            await ctx.respond(f"Default nick set to `{nick}`.", ephemeral=True)

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
