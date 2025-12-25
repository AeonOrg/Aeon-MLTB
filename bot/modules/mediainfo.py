from os import getcwd
from os import path as ospath
from re import search as re_search
from shlex import split as ssplit

import aiohttp
from aiofiles import open as aiopen
from aiofiles.os import mkdir
from aiofiles.os import path as aiopath
from aiofiles.os import remove as aioremove

from bot import LOGGER
from bot.core.telegram_manager import TgClient
from bot.helper.aeon_utils.access_check import token_check
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    edit_message,
    send_message,
)

section_dict = {"General", "Video", "Audio", "Text", "Image"}


def parseinfo(out, file_size):
    tc = ""
    skip = False
    file_size_line = f"File size                              : {file_size / (1024 * 1024):.2f} MiB"

    for line in out.split("\n"):
        if line.startswith("Menu"):
            skip = True
        elif any(line.startswith(section) for section in section_dict):
            skip = False
            if not line.startswith("General"):
                tc += "</pre><br>"
            tc += f"<blockquote>{line.replace('Text', 'Subtitle')}</blockquote><pre>"
        if not skip:
            if line.startswith("File size"):
                line = file_size_line
            key, sep, value = line.partition(":")
            tc += f"{key.strip():<28}{sep} {value.strip()}\n"
    tc += "</pre><br>"
    return tc


async def gen_mediainfo(message, link=None, media=None, msg=None):
    temp_send = await send_message(message, "Generating MediaInfo...")
    try:
        path = "Mediainfo/"
        if not await aiopath.isdir(path):
            await mkdir(path)

        file_size = 0
        if link:
            filename = re_search(".+/(.+)", link).group(1)
            des_path = ospath.join(path, filename)
            headers = {
                "user-agent": "Mozilla/5.0 (Linux; Android 12; 2201116PI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36",
            }
            async with (
                aiohttp.ClientSession() as session,
                session.get(link, headers=headers) as response,
                aiopen(des_path, "wb") as f,
            ):
                file_size = int(response.headers.get("Content-Length", 0))
                async with aiopen(des_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(10000000):
                        await f.write(chunk)
                        break
        elif media:
            des_path = ospath.join(path, media.file_name)
            file_size = media.file_size
            if file_size <= 30000000:
                await msg.download(ospath.join(getcwd(), des_path))
            else:
                async for chunk in TgClient.bot.stream_media(media, limit=3):
                    async with aiopen(des_path, "ab") as f:
                        await f.write(chunk)

        stdout, _, _ = await cmd_exec(ssplit(f'mediainfo "{des_path}"'))

        tc = f"<h4>{ospath.basename(des_path)}</h4><br><br>"
        if stdout:
            tc += parseinfo(stdout, file_size)

    except Exception as e:
        LOGGER.error(e)
        await edit_message(temp_send, f"MediaInfo stopped due to {e!s}")
    finally:
        await aioremove(des_path)

    link_id = (await telegraph.create_page(title="MediaInfo", content=tc))["path"]
    await temp_send.edit(
        f"<blockquote>MediaInfo generated successfully<a href='https://graph.org/{link_id}'>.</a></blockquote>",
        disable_web_page_preview=False,
    )


async def mediainfo(_, message):
    user_id = message.from_user.id
    buttons = ButtonMaker()
    if message.chat.type != message.chat.type.PRIVATE:
        msg, buttons = await token_check(user_id, buttons)
        if msg is not None:
            reply_message = await send_message(message, msg, buttons.build_menu(1))
            await delete_links(message)
            await auto_delete_message(reply_message, time=300)
            return
    reply = message.reply_to_message
    help_msg = (
        "<b>By replying to media:</b>"
        f"\n<code>/{BotCommands.MediaInfoCommand} media </code>"
        "\n\n<b>By reply/sending download link:</b>"
        f"\n<code>/{BotCommands.MediaInfoCommand} link </code>"
    )
    if len(message.command) > 1 or (reply and reply.text):
        link = reply.text if reply else message.command[1]
        await gen_mediainfo(message, link)
    elif reply:
        if file := next(
            (i for i in [reply.document, reply.video, reply.audio] if i),
            None,
        ):
            await gen_mediainfo(message, None, file, reply)
        else:
            await send_message(message, help_msg)
    else:
        await send_message(message, help_msg)
