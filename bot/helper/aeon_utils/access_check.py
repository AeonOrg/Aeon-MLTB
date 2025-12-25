from re import IGNORECASE, escape, search
from time import time
from uuid import uuid4

from pyrogram.errors import PeerIdInvalid, RPCError, UserNotParticipant

from bot import (
    LOGGER,
    user_data,
)
from bot.core.config_manager import Config
from bot.core.telegram_manager import TgClient
from bot.helper.aeon_utils.shorteners import short
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.help_messages import nsfw_keywords
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker


async def error_check(message):
    """
    Performs various access checks for a user and message.

    Checks include:
    - Forced subscription (FSUB_IDS).
    - If the user has initiated a private message with the bot.
    - Token validity (expiry, generation of new tokens).
    - NSFW content in the message.

    Returns:
        A tuple (final_msg, button) where final_msg is a formatted
        error/info message string for the user (or None if no issues),
        and button is a ButtonMaker object with relevant buttons (or None).
    """
    msg, button = [], None
    user = message.from_user or message.sender_chat
    user_id = user.id
    token_timeout = Config.TOKEN_TIMEOUT
    if Config.RSS_CHAT and user_id == int(Config.RSS_CHAT):
        return None, None

    if message.chat.type != message.chat.type.BOT:
        if FSUB_IDS := Config.FSUB_IDS:
            join_button = {}
            for channel_id in FSUB_IDS.split():
                chat = await get_chat_info(int(channel_id))
                if not chat:
                    continue

                try:
                    await chat.get_member(message.from_user.id)
                except UserNotParticipant:
                    invite_link = (
                        f"https://t.me/{chat.username}"
                        if chat.username
                        else chat.invite_link
                    )
                    join_button[chat.title] = invite_link
                except RPCError as e:
                    LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
                except Exception as e:
                    LOGGER.error(f"{e} for {channel_id}")

            if join_button:
                button = button or ButtonMaker()
                for title, link in join_button.items():
                    button.url_button(f"Join {title}", link, "footer")
                msg.append("You haven't joined our channel/group yet!")

        if not token_timeout or user_id in {
            Config.OWNER_ID,
            user_data.get(user_id, {}).get("SUDO"),
        }:
            try:
                temp_msg = await message._client.send_message(
                    chat_id=user_id,
                    text="<b>Checking Access...</b>",
                )
                await temp_msg.delete()
            except Exception:
                button = button or ButtonMaker()
                button.data_button("Start", f"aeon {user_id} private", "header")
                msg.append("You haven't initiated the bot in a private message!")

    if user_id not in {
        Config.OWNER_ID,
        Config.RSS_CHAT,
        user_data.get(user_id, {}).get("SUDO"),
    }:
        token_msg, button = await token_check(user_id, button)
        if token_msg:
            msg.append(token_msg)

    if await nsfw_precheck(message):
        msg.append("NSFW detected")

    if msg:
        username = message.from_user.username
        tag = f"@{username}" if username else message.from_user.mention
        final_msg = f"Hey, <b>{tag}</b>!\n"
        for i, m in enumerate(msg, 1):
            final_msg += f"\n<blockquote><b>{i}</b>: {m}</blockquote>"

        if button:
            button = button.build_menu(2)
        return final_msg, button

    return None, None


async def get_chat_info(channel_id):
    """Gets chat information for the given channel ID.

    Args:
        channel_id: The ID of the channel.

    Returns:
        A Chat object if found, otherwise None.
    """
    try:
        return await TgClient.bot.get_chat(channel_id)
    except PeerIdInvalid as e:
        LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
        return None


def is_nsfw(text):
    """Checks if the given text contains NSFW keywords.

    Args:
        text: The text to check.

    Returns:
        True if NSFW keywords are found, False otherwise.
    """
    pattern = (
        r"(?:^|\W|_)(?:"
        + "|".join(escape(keyword) for keyword in nsfw_keywords)
        + r")(?:$|\W|_)"
    )
    return bool(search(pattern, text, flags=IGNORECASE))


def is_nsfw_data(data):
    """Checks if the given data (list or dict from torrent info) contains NSFW content.

    Args:
        data: A list of items (strings or dicts with 'name') or a dict
              with 'contents' (list of dicts with 'filename').

    Returns:
        True if NSFW content is found, False otherwise.
    """
    if isinstance(data, list):
        return any(
            is_nsfw(item.get("name", ""))
            if isinstance(item, dict)
            else is_nsfw(item)
            for item in data
        )
    if isinstance(data, dict):
        return any(is_nsfw(item["filename"]) for item in data.get("contents", []))
    return False


async def nsfw_precheck(message):
    """Performs a pre-check for NSFW content in the message text or replied-to message.

    Args:
        message: The Pyrogram message object.

    Returns:
        True if NSFW content is detected, False otherwise.
    """
    if is_nsfw(message.text):
        return True

    reply_to = message.reply_to_message
    if not reply_to:
        return False

    for attr in ["document", "video"]:
        if hasattr(reply_to, attr) and getattr(reply_to, attr):
            file_name = getattr(reply_to, attr).file_name
            if file_name and is_nsfw(file_name):
                return True

    return any(
        is_nsfw(getattr(reply_to, attr))
        for attr in ["caption", "text"]
        if hasattr(reply_to, attr) and getattr(reply_to, attr)
    )


async def check_is_paid(chat, uid):
    """Checks if a user is a member of the specified paid chat.

    Args:
        chat: The Pyrogram Chat object of the paid channel/group.
        uid: The user ID to check.

    Returns:
        True if the user is a member, False otherwise.
    """
    try:
        await chat.get_member(uid)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        LOGGER.error(f"{e} for {chat.id}")
        return False


async def is_paid(user_id):
    """Checks if a user is considered 'paid' by verifying membership in PAID_CHANNEL_ID.

    Args:
        user_id: The user ID to check.

    Returns:
        True if the user is considered paid or if PAID_CHANNEL_ID is not set,
        False otherwise.
    """
    if chat := await get_chat_info(Config.PAID_CHANNEL_ID):
        return await check_is_paid(chat, user_id)
    return True


async def token_check(user_id, button=None):
    """
    Checks token validity for a user. If expired or non-existent,
    generates a new token and message/button for collection.

    Args:
        user_id: The user ID to check the token for.
        button: An optional existing ButtonMaker instance to append to.

    Returns:
        A tuple (message_string, button_maker_instance) or (None, None).
    """
    token_timeout = Config.TOKEN_TIMEOUT
    if not token_timeout or user_id == Config.OWNER_ID:
        return None, button
    if Config.PAID_CHANNEL_ID and await is_paid(user_id):
        return None, button

    user_data.setdefault(user_id, {})
    data = user_data[user_id]
    data["TIME"] = await database.get_token_expiry(user_id)
    expire = data.get("TIME")
    isExpired = expire is None or (time() - expire) > token_timeout
    if isExpired:
        token = data["TOKEN"] if expire is None and "TOKEN" in data else str(uuid4())
        if expire is not None:
            del data["TIME"]
        data["TOKEN"] = token
        await database.update_user_token(user_id, token)
        user_data[user_id] = data

        time_str = get_readable_time(token_timeout, True)
        button = button or ButtonMaker()
        short_link = await short(
            f"https://telegram.me/{TgClient.NAME}?start={token}",
        )
        button.url_button("Collect token", short_link)
        msg = "Your token has expired, please collect a new token"
        if Config.PAID_CHANNEL_ID and Config.PAID_CHANNEL_LINK:
            msg += " or subscribe to the paid channel for token-free access."
            button.url_button("Subscribe", Config.PAID_CHANNEL_LINK)

        return (msg + f"\n<b>It will expire after {time_str}</b>!"), button

    return None, button
