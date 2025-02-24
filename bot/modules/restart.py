import contextlib
from asyncio import create_subprocess_exec, gather
from os import execl as osexecl
from sys import executable

from aiofiles import open as aiopen
from aiofiles.os import path as aiopath
from aiofiles.os import remove

from bot import LOGGER, intervals, sabnzbd_client, scheduler
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.core.jdownloader_booter import jdownloader
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.files_utils import clean_all
from bot.helper.telegram_helper import button_build
from bot.helper.telegram_helper.message_utils import delete_message, send_message


@new_task
async def restart_bot(_, message):
    buttons = button_build.ButtonMaker()
    buttons.data_button("Yes!", "botrestart confirm")
    buttons.data_button("Cancel", "botrestart cancel")
    button = buttons.build_menu(2)
    await send_message(
        message,
        "Are you sure you want to restart the bot ?!",
        button,
    )


@new_task
async def restart_sessions(_, message):
    buttons = button_build.ButtonMaker()
    buttons.data_button("Yes!", "sessionrestart confirm")
    buttons.data_button("Cancel", "sessionrestart cancel")
    button = buttons.build_menu(2)
    await send_message(
        message,
        "Are you sure you want to restart the session(s) ?!",
        button,
    )


async def send_incomplete_task_message(cid, msg_id, msg):
    try:
        if msg.startswith("Restarted Successfully!"):
            await TgClient.bot.edit_message_text(
                chat_id=cid,
                message_id=msg_id,
                text=msg,
                disable_web_page_preview=True,
            )
            await remove(".restartmsg")
        else:
            await TgClient.bot.send_message(
                chat_id=cid,
                text=msg,
                disable_web_page_preview=True,
                disable_notification=True,
            )
    except Exception as e:
        LOGGER.error(e)


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        async with aiopen(".restartmsg") as f:
            content = await f.read()
            chat_id, msg_id = map(int, content.splitlines())
    else:
        chat_id, msg_id = 0, 0

    if (
        Config.INCOMPLETE_TASK_NOTIFIER
        and Config.DATABASE_URL
        and (notifier_dict := await database.get_incomplete_tasks())
    ):
        for cid, data in notifier_dict.items():
            msg = "Restarted Successfully!" if cid == chat_id else "Bot Restarted!"
            for tag, links in data.items():
                msg += f"\n\n{tag}: "
                for index, link in enumerate(links, start=1):
                    msg += f" <a href='{link}'>{index}</a> |"
                    if len(msg.encode()) > 4000:
                        await send_incomplete_task_message(cid, msg_id, msg)
                        msg = ""
            if msg:
                await send_incomplete_task_message(cid, msg_id, msg)

    if await aiopath.isfile(".restartmsg"):
        with contextlib.suppress(Exception):
            await TgClient.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="Restarted Successfully!",
            )
        await remove(".restartmsg")


@new_task
async def confirm_restart(_, query):
    await query.answer()
    data = query.data.split()
    message = query.message
    await delete_message(message)
    if data[1] == "confirm":
        reply_to = message.reply_to_message
        intervals["stopAll"] = True
        restart_message = await send_message(reply_to, "Restarting...")
        await delete_message(message)
        await TgClient.stop()
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if qb := intervals["qb"]:
            qb.cancel()
        if jd := intervals["jd"]:
            jd.cancel()
        if nzb := intervals["nzb"]:
            nzb.cancel()
        if st := intervals["status"]:
            for intvl in list(st.values()):
                intvl.cancel()
        await clean_all()
        await TorrentManager.close_all()
        if sabnzbd_client.LOGGED_IN:
            await gather(
                sabnzbd_client.pause_all(),
                sabnzbd_client.delete_job("all", True),
                sabnzbd_client.purge_all(True),
                sabnzbd_client.delete_history("all", delete_files=True),
            )
            await sabnzbd_client.close()
        if jdownloader.is_connected:
            await gather(
                jdownloader.device.downloadcontroller.stop_downloads(),
                jdownloader.device.linkgrabber.clear_list(),
                jdownloader.device.downloads.cleanup(
                    "DELETE_ALL",
                    "REMOVE_LINKS_AND_DELETE_FILES",
                    "ALL",
                ),
            )
            await jdownloader.close()
        proc1 = await create_subprocess_exec(
            "pkill",
            "-9",
            "-f",
            "gunicorn|xria|xnox|xtra|xone|xnzb|java|7z|split",
        )
        proc2 = await create_subprocess_exec("python3", "update.py")
        await gather(proc1.wait(), proc2.wait())
        async with aiopen(".restartmsg", "w") as f:
            await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
        osexecl(executable, executable, "-m", "bot")
    else:
        await delete_message(message)
