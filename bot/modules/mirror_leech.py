# ruff: noqa: RUF006
from asyncio import create_task
from base64 import b64encode
from re import match as re_match

from aiofiles.os import path as aiopath

from bot import DOWNLOAD_DIR, LOGGER, bot_loop, task_dict_lock
from bot.core.aeon_client import TgClient
from bot.helper.aeon_utils.access_check import error_check
from bot.helper.ext_utils.bot_utils import (
    COMMAND_USAGE,
    arg_parser,
    get_content_type,
    sync_to_async,
)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.links_utils import (
    is_gdrive_id,
    is_gdrive_link,
    is_magnet,
    is_rclone_path,
    is_telegram_link,
    is_url,
)
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.mirror_leech_utils.download_utils.aria2_download import (
    add_aria2_download,
)
from bot.helper.mirror_leech_utils.download_utils.direct_downloader import (
    add_direct_download,
)
from bot.helper.mirror_leech_utils.download_utils.direct_link_generator import (
    direct_link_generator,
)
from bot.helper.mirror_leech_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_leech_utils.download_utils.jd_download import add_jd_download
from bot.helper.mirror_leech_utils.download_utils.nzb_downloader import add_nzb
from bot.helper.mirror_leech_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_leech_utils.download_utils.rclone_download import (
    add_rclone_download,
)
from bot.helper.mirror_leech_utils.download_utils.telegram_download import (
    TelegramDownloadHelper,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    get_tg_link_message,
    send_message,
)


class Mirror(TaskListener):
    def __init__(
        self,
        client,
        message,
        is_qbit=False,
        is_leech=False,
        is_jd=False,
        is_nzb=False,
        same_dir=None,
        bulk=None,
        multi_tag=None,
        options="",
    ):
        if same_dir is None:
            same_dir = {}
        if bulk is None:
            bulk = []
        self.message = message
        self.client = client
        self.multi_tag = multi_tag
        self.options = options
        self.same_dir = same_dir
        self.bulk = bulk
        super().__init__()
        self.is_qbit = is_qbit
        self.is_leech = is_leech
        self.is_jd = is_jd
        self.is_nzb = is_nzb

    async def new_event(self):
        text = self.message.text.split("\n")
        input_list = text[0].split(" ")
        error_msg, error_button = await error_check(self.message)
        if error_msg:
            await delete_links(self.message)
            error = await send_message(self.message, error_msg, error_button)
            return await auto_delete_message(error, time=300)
        user_id = self.message.from_user.id if self.message.from_user else ""
        args = {
            "-doc": False,
            "-med": False,
            "-d": False,
            "-j": False,
            "-s": False,
            "-b": False,
            "-e": False,
            "-z": False,
            "-sv": False,
            "-ss": False,
            "-f": False,
            "-fd": False,
            "-fu": False,
            "-hl": False,
            "-bt": False,
            "-ut": False,
            "-i": 0,
            "-sp": 0,
            "link": "",
            "-n": "",
            "-m": "",
            "-up": "",
            "-rcf": "",
            "-au": "",
            "-ap": "",
            "-h": "",
            "-t": "",
            "-ca": "",
            "-cv": "",
            "-ns": "",
            "-md": "",
            "-tl": "",
            "-ff": set(),
        }

        arg_parser(input_list[1:], args)

        self.select = args["-s"]
        self.seed = args["-d"]
        self.name = args["-n"]
        self.up_dest = args["-up"]
        self.rc_flags = args["-rcf"]
        self.link = args["link"]
        self.compress = args["-z"]
        self.extract = args["-e"]
        self.join = args["-j"]
        self.thumb = args["-t"]
        self.split_size = args["-sp"]
        self.sample_video = args["-sv"]
        self.screen_shots = args["-ss"]
        self.force_run = args["-f"]
        self.force_download = args["-fd"]
        self.force_upload = args["-fu"]
        self.convert_audio = args["-ca"]
        self.convert_video = args["-cv"]
        self.name_sub = args["-ns"]
        self.hybrid_leech = args["-hl"]
        self.thumbnail_layout = args["-tl"]
        self.as_doc = args["-doc"]
        self.as_med = args["-med"]
        self.metadata = args["-md"]
        self.folder_name = (
            f"/{args['-m']}".rstrip("/") if len(args["-m"]) > 0 else ""
        )
        self.bot_trans = args["-bt"]
        self.user_trans = args["-ut"]

        headers = args["-h"]
        is_bulk = args["-b"]

        bulk_start = 0
        bulk_end = 0
        ratio = None
        seed_time = None
        reply_to = None
        file_ = None
        session = TgClient.bot

        try:
            self.multi = int(args["-i"])
        except Exception:
            self.multi = 0

        try:
            if args["-ff"]:
                if isinstance(args["-ff"], set):
                    self.ffmpeg_cmds = args["-ff"]
                else:
                    self.ffmpeg_cmds = eval(args["-ff"])
        except Exception as e:
            self.ffmpeg_cmds = None
            LOGGER.error(e)

        if not isinstance(self.seed, bool):
            dargs = self.seed.split(":")
            ratio = dargs[0] or None
            if len(dargs) == 2:
                seed_time = dargs[1] or None
            self.seed = True

        if not isinstance(is_bulk, bool):
            dargs = is_bulk.split(":")
            bulk_start = dargs[0] or 0
            if len(dargs) == 2:
                bulk_end = dargs[1] or 0
            is_bulk = True

        if not is_bulk:
            if self.multi > 0:
                if self.folder_name:
                    async with task_dict_lock:
                        if self.folder_name in self.same_dir:
                            self.same_dir[self.folder_name]["tasks"].add(self.mid)
                            for fd_name in self.same_dir:
                                if fd_name != self.folder_name:
                                    self.same_dir[fd_name]["total"] -= 1
                        elif self.same_dir:
                            self.same_dir[self.folder_name] = {
                                "total": self.multi,
                                "tasks": {self.mid},
                            }
                            for fd_name in self.same_dir:
                                if fd_name != self.folder_name:
                                    self.same_dir[fd_name]["total"] -= 1
                        else:
                            self.same_dir = {
                                self.folder_name: {
                                    "total": self.multi,
                                    "tasks": {self.mid},
                                },
                            }
                elif self.same_dir:
                    async with task_dict_lock:
                        for fd_name in self.same_dir:
                            self.same_dir[fd_name]["total"] -= 1
        else:
            await self.init_bulk(input_list, bulk_start, bulk_end, Mirror)
            return None

        if len(self.bulk) != 0:
            del self.bulk[0]

        await self.run_multi(input_list, Mirror)

        await self.get_tag(text)

        path = f"{DOWNLOAD_DIR}{self.mid}{self.folder_name}"

        if (
            not self.link
            and (reply_to := self.message.reply_to_message)
            and reply_to.text
        ):
            self.link = reply_to.text.split("\n", 1)[0].strip()
        if is_telegram_link(self.link):
            try:
                reply_to, session = await get_tg_link_message(self.link, user_id)
            except Exception as e:
                x = await send_message(self.message, f"ERROR: {e}")
                await self.remove_from_same_dir()
                await delete_links(self.message)
                return await auto_delete_message(x, time=300)

        if isinstance(reply_to, list):
            self.bulk = reply_to
            b_msg = input_list[:1]
            self.options = " ".join(input_list[1:])
            b_msg.append(f"{self.bulk[0]} -i {len(self.bulk)} {self.options}")
            nextmsg = await send_message(self.message, " ".join(b_msg))
            nextmsg = await self.client.get_messages(
                chat_id=self.message.chat.id,
                message_ids=nextmsg.id,
            )
            if self.message.from_user:
                nextmsg.from_user = self.user
            else:
                nextmsg.sender_chat = self.user
            await Mirror(
                self.client,
                nextmsg,
                self.is_qbit,
                self.is_leech,
                self.is_jd,
                self.is_nzb,
                self.same_dir,
                self.bulk,
                self.multi_tag,
                self.options,
            ).new_event()
            return await delete_links(self.message)

        if reply_to:
            file_ = (
                reply_to.document
                or reply_to.photo
                or reply_to.video
                or reply_to.audio
                or reply_to.voice
                or reply_to.video_note
                or reply_to.sticker
                or reply_to.animation
                or None
            )

            if file_ is None:
                if reply_text := reply_to.text:
                    self.link = reply_text.split("\n", 1)[0].strip()
                else:
                    reply_to = None
            elif reply_to.document and (
                file_.mime_type == "application/x-bittorrent"
                or file_.file_name.endswith((".torrent", ".dlc", ".nzb"))
            ):
                self.link = await reply_to.download()
                file_ = None

        try:
            if (
                self.link
                and (is_magnet(self.link) or self.link.endswith(".torrent"))
            ) or (
                file_ and file_.file_name and file_.file_name.endswith(".torrent")
            ):
                self.is_qbit = True
        except Exception:
            pass

        if (
            (not self.link and file_ is None)
            or (is_telegram_link(self.link) and reply_to is None)
            or (
                file_ is None
                and not is_url(self.link)
                and not is_magnet(self.link)
                and not await aiopath.exists(self.link)
                and not is_rclone_path(self.link)
                and not is_gdrive_id(self.link)
                and not is_gdrive_link(self.link)
            )
        ):
            x = await send_message(
                self.message,
                COMMAND_USAGE["mirror"][0],
                COMMAND_USAGE["mirror"][1],
            )
            await self.remove_from_same_dir()
            await delete_links(self.message)
            return await auto_delete_message(x, time=300)

        if len(self.link) > 0:
            LOGGER.info(self.link)

        try:
            await self.before_start()
        except Exception as e:
            x = await send_message(self.message, e)
            await self.remove_from_same_dir()
            await delete_links(self.message)
            return await auto_delete_message(x, time=300)

        if (
            not self.is_jd
            and not self.is_qbit
            and not self.is_nzb
            and not is_magnet(self.link)
            and not is_rclone_path(self.link)
            and not is_gdrive_link(self.link)
            and not self.link.endswith(".torrent")
            and file_ is None
            and not is_gdrive_id(self.link)
        ):
            content_type = await get_content_type(self.link)
            if content_type is None or re_match(
                r"text/html|text/plain",
                content_type,
            ):
                try:
                    self.link = await sync_to_async(direct_link_generator, self.link)
                    if isinstance(self.link, tuple):
                        self.link, headers = self.link
                    elif isinstance(self.link, str):
                        LOGGER.info(f"Generated link: {self.link}")
                except DirectDownloadLinkException as e:
                    e = str(e)
                    if "This link requires a password!" not in e:
                        LOGGER.info(e)
                    if e.startswith("ERROR:"):
                        x = await send_message(self.message, e)
                        await self.remove_from_same_dir()
                        await delete_links(self.message)
                        return await auto_delete_message(x, time=300)
                except Exception as e:
                    x = await send_message(self.message, e)
                    await self.remove_from_same_dir()
                    await delete_links(self.message)
                    return await auto_delete_message(x, time=300)

        if file_ is not None:
            create_task(
                TelegramDownloadHelper(self).add_download(
                    reply_to,
                    f"{path}/",
                    session,
                ),
            )
        elif isinstance(self.link, dict):
            create_task(add_direct_download(self, path))
        elif self.is_jd:
            create_task(add_jd_download(self, path))
        elif self.is_qbit:
            create_task(add_qb_torrent(self, path, ratio, seed_time))
        elif self.is_nzb:
            create_task(add_nzb(self, path))
        elif is_rclone_path(self.link):
            create_task(add_rclone_download(self, f"{path}/"))
        elif is_gdrive_link(self.link) or is_gdrive_id(self.link):
            create_task(add_gd_download(self, path))
        else:
            ussr = args["-au"]
            pssw = args["-ap"]
            if ussr or pssw:
                auth = f"{ussr}:{pssw}"
                headers += f" authorization: Basic {b64encode(auth.encode()).decode('ascii')}"
            create_task(add_aria2_download(self, path, headers, ratio, seed_time))
        await delete_links(self.message)
        return None


async def mirror(client, message):
    bot_loop.create_task(Mirror(client, message).new_event())


async def leech(client, message):
    bot_loop.create_task(Mirror(client, message, is_leech=True).new_event())


async def jd_mirror(client, message):
    bot_loop.create_task(Mirror(client, message, is_jd=True).new_event())


async def nzb_mirror(client, message):
    bot_loop.create_task(Mirror(client, message, is_nzb=True).new_event())


async def jd_leech(client, message):
    bot_loop.create_task(
        Mirror(client, message, is_leech=True, is_jd=True).new_event(),
    )


async def nzb_leech(client, message):
    bot_loop.create_task(
        Mirror(client, message, is_leech=True, is_nzb=True).new_event(),
    )
