# ruff: noqa: F405
from pyrogram.filters import command, regex
from pyrogram.handlers import (
    CallbackQueryHandler,
    EditedMessageHandler,
    MessageHandler,
)

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.modules import *

from .aeon_client import TgClient


def add_handlers():
    command_filters = {
        "authorize": (
            authorize,
            BotCommands.AuthorizeCommand,
            CustomFilters.sudo,
        ),
        "unauthorize": (
            unauthorize,
            BotCommands.UnAuthorizeCommand,
            CustomFilters.sudo,
        ),
        "add_sudo": (
            add_sudo,
            BotCommands.AddSudoCommand,
            CustomFilters.sudo,
        ),
        "remove_sudo": (
            remove_sudo,
            BotCommands.RmSudoCommand,
            CustomFilters.sudo,
        ),
        "send_bot_settings": (
            send_bot_settings,
            BotCommands.BotSetCommand,
            CustomFilters.sudo,
        ),
        "cancel_all_buttons": (
            cancel_all_buttons,
            BotCommands.CancelAllCommand,
            CustomFilters.authorized,
        ),
        "clone_node": (
            clone_node,
            BotCommands.CloneCommand,
            CustomFilters.authorized,
        ),
        "aioexecute": (
            aioexecute,
            BotCommands.AExecCommand,
            CustomFilters.sudo,
        ),
        "execute": (
            execute,
            BotCommands.ExecCommand,
            CustomFilters.sudo,
        ),
        "clear": (
            clear,
            BotCommands.ClearLocalsCommand,
            CustomFilters.sudo,
        ),
        "select": (
            select,
            BotCommands.SelectCommand,
            CustomFilters.authorized,
        ),
        "remove_from_queue": (
            remove_from_queue,
            BotCommands.ForceStartCommand,
            CustomFilters.authorized,
        ),
        "count_node": (
            count_node,
            BotCommands.CountCommand,
            CustomFilters.authorized,
        ),
        "delete_file": (
            delete_file,
            BotCommands.DeleteCommand,
            CustomFilters.authorized,
        ),
        "gdrive_search": (
            gdrive_search,
            BotCommands.ListCommand,
            CustomFilters.authorized,
        ),
        "mirror": (
            mirror,
            BotCommands.MirrorCommand,
            CustomFilters.authorized,
        ),
        "jd_mirror": (
            jd_mirror,
            BotCommands.JdMirrorCommand,
            CustomFilters.authorized,
        ),
        "leech": (
            leech,
            BotCommands.LeechCommand,
            CustomFilters.authorized,
        ),
        "jd_leech": (
            jd_leech,
            BotCommands.JdLeechCommand,
            CustomFilters.authorized,
        ),
        "get_rss_menu": (
            get_rss_menu,
            BotCommands.RssCommand,
            CustomFilters.authorized,
        ),
        "run_shell": (
            run_shell,
            BotCommands.ShellCommand,
            CustomFilters.owner,
        ),
        "start": (
            start,
            BotCommands.StartCommand,
            None,
        ),
        "log": (
            log,
            BotCommands.LogCommand,
            CustomFilters.sudo,
        ),
        "restart_bot": (
            restart_bot,
            BotCommands.RestartCommand,
            CustomFilters.sudo,
        ),
        "ping": (
            ping,
            BotCommands.PingCommand,
            CustomFilters.authorized,
        ),
        "bot_help": (
            bot_help,
            BotCommands.HelpCommand,
            CustomFilters.authorized,
        ),
        "bot_stats": (
            bot_stats,
            BotCommands.StatsCommand,
            CustomFilters.authorized,
        ),
        "task_status": (
            task_status,
            BotCommands.StatusCommand,
            CustomFilters.authorized,
        ),
        "torrent_search": (
            torrent_search,
            BotCommands.SearchCommand,
            CustomFilters.authorized,
        ),
        "get_users_settings": (
            get_users_settings,
            BotCommands.UsersCommand,
            CustomFilters.sudo,
        ),
        "send_user_settings": (
            send_user_settings,
            BotCommands.UserSetCommand,
            CustomFilters.authorized,
        ),
        "ytdl": (
            ytdl,
            BotCommands.YtdlCommand,
            CustomFilters.authorized,
        ),
        "ytdl_leech": (
            ytdl_leech,
            BotCommands.YtdlLeechCommand,
            CustomFilters.authorized,
        ),
        #    "restart_sessions": (
        #        restart_sessions,
        #        BotCommands.RestartSessionsCommand,
        #        CustomFilters.sudo,
        #    ),
        "mediainfo": (
            mediainfo,
            BotCommands.MediaInfoCommand,
            CustomFilters.authorized,
        ),
        "speedtest": (
            speedtest,
            BotCommands.SpeedTest,
            CustomFilters.authorized,
        ),
        "broadcast": (
            broadcast,
            BotCommands.BroadcastCommand,
            CustomFilters.owner,
        ),
        "nzb_mirror": (
            nzb_mirror,
            BotCommands.NzbMirrorCommand,
            CustomFilters.authorized,
        ),
        "nzb_leech": (
            nzb_leech,
            BotCommands.NzbLeechCommand,
            CustomFilters.authorized,
        ),
        "hydra_search": (
            hydra_search,
            BotCommands.HydraSearchCommamd,
            CustomFilters.authorized,
        ),
    }

    for handler_func, command_name, custom_filter in command_filters.values():
        if custom_filter:
            filters_to_apply = (
                command(command_name, case_sensitive=True) & custom_filter
            )
        else:
            filters_to_apply = command(command_name, case_sensitive=True)

        TgClient.bot.add_handler(
            MessageHandler(
                handler_func,
                filters=filters_to_apply,
            ),
        )

    regex_filters = {
        "^botset": edit_bot_settings,
        "^canall": cancel_all_update,
        "^stopm": cancel_multi,
        "^sel": confirm_selection,
        "^list_types": select_type,
        "^rss": rss_listener,
        "^torser": torrent_search_update,
        "^userset": edit_user_settings,
        "^help": arg_usage,
        "^status": status_pages,
        "^botrestart": confirm_restart,
        "^aeon": aeon_callback,
    }

    for regex_filter, handler_func in regex_filters.items():
        TgClient.bot.add_handler(
            CallbackQueryHandler(handler_func, filters=regex(regex_filter)),
        )

    TgClient.bot.add_handler(
        EditedMessageHandler(
            run_shell,
            filters=command(BotCommands.ShellCommand, case_sensitive=True)
            & CustomFilters.owner,
        ),
    )
    TgClient.bot.add_handler(
        MessageHandler(
            cancel,
            filters=regex(r"^/stop(_\w+)?(?!all)") & CustomFilters.authorized,
        ),
    )
