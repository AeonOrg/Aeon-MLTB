from asyncio import gather, sleep
from re import match as re_match
from time import time

from cachetools import TTLCache
from pyrogram import Client, enums
from pyrogram.errors import (
    FloodPremiumWait,
    FloodWait,
    MessageEmpty,
    MessageNotModified,
)
from pyrogram.types import InputMediaPhoto

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    intervals,
    status_dict,
    task_dict_lock,
    user_data,
)
from bot.core.config_manager import Config
from bot.core.telegram_manager import TgClient
from bot.helper.ext_utils.bot_utils import SetInterval
from bot.helper.ext_utils.exceptions import TgLinkException
from bot.helper.ext_utils.status_utils import get_readable_message

session_cache = TTLCache(maxsize=1000, ttl=36000)


async def send_message(
    message,
    text,
    buttons=None,
    photo=None,
    markdown=False,
    block=True,
):
    parse_mode = enums.ParseMode.MARKDOWN if markdown else enums.ParseMode.HTML
    try:
        if isinstance(message, int):
            return await TgClient.bot.send_message(
                chat_id=message,
                text=text,
                disable_notification=True,
                reply_markup=buttons,
                parse_mode=parse_mode,
            )
        if photo:
            return await message.reply_photo(
                photo=photo,
                reply_to_message_id=message.id,
                caption=text,
                reply_markup=buttons,
                disable_notification=True,
                parse_mode=parse_mode,
            )
        return await message.reply(
            text=text,
            quote=True,
            disable_notification=True,
            reply_markup=buttons,
            parse_mode=parse_mode,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        if not block:
            return message
        await sleep(f.value * 1.2)
        return await send_message(message, text, buttons, photo, markdown)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def edit_message(
    message,
    text,
    buttons=None,
    photo=None,
    markdown=False,
    block=True,
):
    # parse_mode = enums.ParseMode.MARKDOWN if markdown else enums.ParseMode.HTML
    try:
        if message.media:
            if photo:
                return await message.edit_media(
                    InputMediaPhoto(photo, text),
                    reply_markup=buttons,
                    # parse_mode=parse_mode,
                )
            return await message.edit_caption(
                caption=text,
                reply_markup=buttons,
                # parse_mode=parse_mode,
            )
        await message.edit(
            text=text,
            reply_markup=buttons,
            # parse_mode=parse_mode,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        if not block:
            return message
        await sleep(f.value * 1.2)
        return await edit_message(message, text, buttons, photo)
    except (MessageNotModified, MessageEmpty):
        pass
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def send_file(message, file, caption="", buttons=None):
    try:
        return await message.reply_document(
            document=file,
            quote=True,
            caption=caption,
            disable_notification=True,
            reply_markup=buttons,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await send_file(message, file, caption, buttons)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def send_rss(text, chat_id, thread_id):
    try:
        app = TgClient.user or TgClient.bot
        return await app.send_message(
            chat_id=chat_id,
            text=text,
            message_thread_id=thread_id,
            disable_notification=True,
        )
    except (FloodWait, FloodPremiumWait) as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await send_rss(text)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def delete_message(*args):
    msgs = [msg.delete() for msg in args if msg]
    results = await gather(*msgs, return_exceptions=True)

    for msg, result in zip(args, results, strict=False):
        if isinstance(result, Exception):
            LOGGER.error(f"Failed to delete message {msg}: {result}", exc_info=True)


async def delete_links(message):
    if not Config.DELETE_LINKS:
        return
    if reply_to := message.reply_to_message:
        await delete_message(reply_to)
    await delete_message(message)


async def auto_delete_message(*args, time=60):
    if time and time > 0:
        await sleep(time)
        await delete_message(*args)


async def delete_status():
    async with task_dict_lock:
        for key, data in list(status_dict.items()):
            try:
                await delete_message(data["message"])
                del status_dict[key]
            except Exception as e:
                LOGGER.error(str(e))


async def get_tg_link_message(link, user_id=""):
    message = None
    links = []
    user_session = None

    if user_id:
        if user_id in session_cache:
            user_session = session_cache[user_id]
        else:
            user_dict = user_data.get(user_id, {})
            session_string = user_dict.get("USER_SESSION")
            if session_string:
                user_session = Client(
                    f"session_{user_id}",
                    Config.TELEGRAM_API,
                    Config.TELEGRAM_HASH,
                    session_string=session_string,
                    no_updates=True,
                )
                await user_session.start()
                session_cache[user_id] = user_session
            else:
                user_session = TgClient.user

    if link.startswith("https://t.me/"):
        private = False
        msg = re_match(
            r"https:\/\/t\.me\/(?:c\/)?([^\/]+)(?:\/[^\/]+)?\/([0-9-]+)",
            link,
        )
    else:
        private = True
        msg = re_match(
            r"tg:\/\/openmessage\?user_id=([0-9]+)&message_id=([0-9-]+)",
            link,
        )
        if not user_session:
            raise TgLinkException(
                "USER_SESSION_STRING required for this private link!",
            )

    chat = msg[1]
    msg_id = msg[2]
    if "-" in msg_id:
        start_id, end_id = map(int, msg_id.split("-"))
        msg_id = start_id
        btw = end_id - start_id
        if private:
            link = link.split("&message_id=")[0]
            links.append(f"{link}&message_id={start_id}")
            for _ in range(btw):
                start_id += 1
                links.append(f"{link}&message_id={start_id}")
        else:
            link = link.rsplit("/", 1)[0]
            links.append(f"{link}/{start_id}")
            for _ in range(btw):
                start_id += 1
                links.append(f"{link}/{start_id}")
    else:
        msg_id = int(msg_id)

    if chat.isdigit():
        chat = int(chat) if private else int(f"-100{chat}")

    if not private:
        try:
            message = await TgClient.bot.get_messages(
                chat_id=chat,
                message_ids=msg_id,
            )
            if message.empty:
                private = True
        except Exception as e:
            private = True
            if not user_session:
                raise e

    if not private:
        return (links, TgClient.bot) if links else (message, TgClient.bot)
    if user_session:
        try:
            user_message = await user_session.get_messages(
                chat_id=chat,
                message_ids=msg_id,
            )
        except Exception as e:
            raise TgLinkException("We don't have access to this chat!") from e
        if not user_message.empty:
            return (links, user_session) if links else (user_message, user_session)
        return None, None
    raise TgLinkException("Private: Please report!")


async def temp_download(msg):
    path = f"{DOWNLOAD_DIR}temp"
    return await msg.download(file_name=f"{path}/")


async def update_status_message(sid, force=False):
    if intervals["stopAll"]:
        return
    async with task_dict_lock:
        if not status_dict.get(sid):
            if obj := intervals["status"].get(sid):
                obj.cancel()
                del intervals["status"][sid]
            return
        if not force and time() - status_dict[sid]["time"] < 3:
            return
        status_dict[sid]["time"] = time()
        page_no = status_dict[sid]["page_no"]
        status = status_dict[sid]["status"]
        is_user = status_dict[sid]["is_user"]
        page_step = status_dict[sid]["page_step"]
        text, buttons = await get_readable_message(
            sid,
            is_user,
            page_no,
            status,
            page_step,
        )
        if text is None:
            del status_dict[sid]
            if obj := intervals["status"].get(sid):
                obj.cancel()
                del intervals["status"][sid]
            return
        if text != status_dict[sid]["message"].text:
            message = await edit_message(
                status_dict[sid]["message"],
                text,
                buttons,
                block=False,
            )
            if isinstance(message, str):
                if message.startswith("Telegram says: [40"):
                    del status_dict[sid]
                    if obj := intervals["status"].get(sid):
                        obj.cancel()
                        del intervals["status"][sid]
                else:
                    LOGGER.error(
                        f"Status with id: {sid} haven't been updated. Error: {message}",
                    )
                return
            status_dict[sid]["message"].text = text
            status_dict[sid]["time"] = time()


async def send_status_message(msg, user_id=0):
    if intervals["stopAll"]:
        return
    sid = user_id or msg.chat.id
    is_user = bool(user_id)
    async with task_dict_lock:
        if sid in status_dict:
            page_no = status_dict[sid]["page_no"]
            status = status_dict[sid]["status"]
            page_step = status_dict[sid]["page_step"]
            text, buttons = await get_readable_message(
                sid,
                is_user,
                page_no,
                status,
                page_step,
            )
            if text is None:
                del status_dict[sid]
                if obj := intervals["status"].get(sid):
                    obj.cancel()
                    del intervals["status"][sid]
                return
            old_message = status_dict[sid]["message"]
            message = await send_message(msg, text, buttons, block=False)
            if isinstance(message, str):
                LOGGER.error(
                    f"Status with id: {sid} haven't been sent. Error: {message}",
                )
                return
            await delete_message(old_message)
            message.text = text
            status_dict[sid].update({"message": message, "time": time()})
        else:
            text, buttons = await get_readable_message(sid, is_user)
            if text is None:
                return
            message = await send_message(msg, text, buttons, block=False)
            if isinstance(message, str):
                LOGGER.error(
                    f"Status with id: {sid} haven't been sent. Error: {message}",
                )
                return
            message.text = text
            status_dict[sid] = {
                "message": message,
                "time": time(),
                "page_no": 1,
                "page_step": 1,
                "status": "All",
                "is_user": is_user,
            }
        if not intervals["status"].get(sid) and not is_user:
            intervals["status"][sid] = SetInterval(
                1,
                update_status_message,
                sid,
            )
