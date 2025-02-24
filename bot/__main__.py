# ruff: noqa: E402
from asyncio import gather

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

# Initialize Configurations
LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

from .core.startup import load_settings

bot_loop.run_until_complete(load_settings())

from .core.aeon_client import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

# Commands and Descriptions
COMMANDS = {
    "MirrorCommand": "- Start mirroring",
    "LeechCommand": "- Start leeching",
    "JdMirrorCommand": "- Mirror using Jdownloader",
    "JdLeechCommand": "- Leech using jdownloader",
    "NzbMirrorCommand": "- Mirror nzb files",
    "NzbLeechCommand": "- Leech nzb files",
    "YtdlCommand": "- Mirror yt-dlp supported link",
    "YtdlLeechCommand": "- Leech through yt-dlp supported link",
    "CloneCommand": "- Copy file/folder to Drive",
    "MediaInfoCommand": "- Get mediainfo",
    "ForceStartCommand": "- Start task from queue",
    "CountCommand": "- Count file/folder on Google Drive",
    "ListCommand": "- Search in Drive",
    "SearchCommand": "- Search in Torrent",
    "UserSetCommand": "- User settings",
    "StatusCommand": "- Get mirror status message",
    "StatsCommand": "- Check Bot & System stats",
    "CancelAllCommand": "- Cancel all tasks added by you to the bot",
    "HelpCommand": "- Get detailed help",
    "SpeedTest": "- Get speedtest result",
    "BotSetCommand": "- [ADMIN] Open Bot settings",
    "LogCommand": "- [ADMIN] View log",
    "RestartCommand": "- [ADMIN] Restart the bot",
    # "RestartSessionsCommand": "- [ADMIN] Restart the session instead of the bot",
}


# Setup Commands
COMMAND_OBJECTS = [
    BotCommand(
        getattr(BotCommands, cmd)[0]
        if isinstance(getattr(BotCommands, cmd), list)
        else getattr(BotCommands, cmd),
        description,
    )
    for cmd, description in COMMANDS.items()
]


# Set Bot Commands
async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


# Main Function
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


# Run Bot
LOGGER.info("Bot Started!")
bot_loop.run_forever()
