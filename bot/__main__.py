# ruff: noqa: E402, PLC0415
from asyncio import gather

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

from .core.startup import load_settings

bot_loop.run_until_complete(load_settings())

from .core.telegram_manager import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

COMMANDS = {
    "MirrorCommand": "- Start mirroring",
    "LeechCommand": "- Start leeching",
    "JdMirrorCommand": "- Mirror using JDownloader",
    "JdLeechCommand": "- Leech using JDownloader",
    "NzbMirrorCommand": "- Mirror NZB files",
    "NzbLeechCommand": "- Leech NZB files",
    "YtdlCommand": "- Mirror link using yt-dlp",
    "YtdlLeechCommand": "- Leech link using yt-dlp",
    "CloneCommand": "- Copy file/folder to Drive",
    "MediaInfoCommand": "- Get media information",
    "SoxCommand": "- Get audio spectrum",
    "ForceStartCommand": "- Force start a task from queue",
    "CountCommand": "- Count file/folder on Google Drive",
    "ListCommand": "- Search in Drive",
    "SearchCommand": "- Search for torrents",
    "UserSetCommand": "- User settings",
    "StatusCommand": "- Show mirror status",
    "StatsCommand": "- Show Bot and System stats",
    "CancelAllCommand": "- Cancel all your tasks",
    "HelpCommand": "- Get detailed help",
    "SpeedTest": "- Run a speedtest",
    "BotSetCommand": "- [ADMIN] Open Bot settings",
    "LogCommand": "- [ADMIN] View bot log",
    "RestartCommand": "- [ADMIN] Restart the bot",
}


COMMAND_OBJECTS = [
    BotCommand(
        getattr(BotCommands, cmd)[0]
        if isinstance(getattr(BotCommands, cmd), list)
        else getattr(BotCommands, cmd),
        description,
    )
    for cmd, description in COMMANDS.items()
]


async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


async def main():
    from .core.startup import (
        load_configurations,
        save_settings,
        update_aria2_options,
        update_nzb_options,
        update_qb_options,
        update_variables,
    )

    await gather(TgClient.start_bot(), TgClient.start_user())
    await gather(load_configurations(), update_variables())
    from .core.torrent_manager import TorrentManager

    await TorrentManager.initiate()
    await gather(
        update_qb_options(),
        update_aria2_options(),
        update_nzb_options(),
    )
    from .core.jdownloader_booter import jdownloader
    from .helper.ext_utils.files_utils import clean_all
    from .helper.ext_utils.telegraph_helper import telegraph
    from .helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
    from .modules import (
        get_packages_version,
        initiate_search_tools,
        restart_notification,
    )

    await gather(
        set_commands(),
        jdownloader.boot(),
    )
    await gather(
        save_settings(),
        clean_all(),
        initiate_search_tools(),
        get_packages_version(),
        restart_notification(),
        telegraph.create_account(),
        rclone_serve_booter(),
    )


bot_loop.run_until_complete(main())

from .core.handlers import add_handlers
from .helper.ext_utils.bot_utils import create_help_buttons
from .helper.listeners.aria2_listener import add_aria2_callbacks

add_aria2_callbacks()
create_help_buttons()
add_handlers()


LOGGER.info("Bot Started!")
bot_loop.run_forever()
