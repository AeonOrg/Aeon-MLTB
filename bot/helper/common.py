import contextlib
import os
from asyncio import gather, sleep
from collections import Counter
from copy import deepcopy
from os import path as ospath
from os import walk
from re import IGNORECASE, findall, sub
from secrets import token_hex
from shlex import split

from aiofiles.os import listdir, makedirs, remove
from aiofiles.os import path as aiopath
from aioshutil import move, rmtree
from pyrogram.enums import ChatAction

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    cpu_eater_lock,
    excluded_extensions,
    intervals,
    multi_tags,
    task_dict,
    task_dict_lock,
    user_data,
)
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.command_gen import (
    get_embed_thumb_cmd,
    get_metadata_cmd,
    get_watermark_cmd,
)

from .ext_utils.bot_utils import get_size_bytes, new_task, sync_to_async
from .ext_utils.bulk_links import extract_bulk_links
from .ext_utils.files_utils import (
    SevenZ,
    get_base_name,
    get_path_size,
    is_archive,
    is_archive_split,
    is_first_archive_split,
    split_file,
)
from .ext_utils.links_utils import (
    is_gdrive_id,
    is_gdrive_link,
    is_rclone_path,
    is_telegram_link,
)
from .ext_utils.media_utils import (
    FFMpeg,
    create_thumb,
    get_document_type,
    is_mkv,
    take_ss,
)
from .mirror_leech_utils.gdrive_utils.list import GoogleDriveList
from .mirror_leech_utils.rclone_utils.list import RcloneList
from .mirror_leech_utils.status_utils.ffmpeg_status import FFmpegStatus
from .mirror_leech_utils.status_utils.sevenz_status import SevenZStatus
from .telegram_helper.message_utils import (
    get_tg_link_message,
    send_message,
    send_status_message,
    temp_download,
)


class TaskConfig:
    """Holds all configuration and state for a single mirror/leech task."""

    def __init__(self):
        """Initializes the TaskConfig object based on the incoming message."""
        self.mid = self.message.id
        self.user = self.message.from_user or self.message.sender_chat
        self.user_id = self.user.id
        self.user_dict = user_data.get(self.user_id, {})
        self.dir = f"{DOWNLOAD_DIR}{self.mid}"
        self.up_dir = ""
        self.link = ""
        self.up_dest = ""
        self.raw_up_dest = ""
        self.rc_flags = ""
        self.tag = ""
        self.name = ""
        self.subname = ""
        self.name_sub = ""
        self.metadata = ""
        self.watermark = ""
        self.thumbnail_layout = ""
        self.folder_name = ""
        self.split_size = 0
        self.max_split_size = 0
        self.multi = 0
        self.size = 0
        self.subsize = 0
        self.proceed_count = 0
        self.is_leech = False
        self.is_jd = False
        self.is_qbit = False
        self.is_nzb = False
        self.is_clone = False
        self.is_ytdlp = False
        self.user_transmission = False
        self.hybrid_leech = False
        self.extract = False
        self.compress = False
        self.select = False
        self.seed = False
        self.compress = False
        self.extract = False
        self.join = False
        self.private_link = False
        self.stop_duplicate = False
        self.sample_video = False
        self.convert_audio = False
        self.convert_video = False
        self.screen_shots = False
        self.is_cancelled = False
        self.force_run = False
        self.force_download = False
        self.force_upload = False
        self.is_torrent = False
        self.as_med = False
        self.as_doc = False
        self.is_file = False
        self.bot_trans = False
        self.user_trans = False
        self.progress = True
        self.ffmpeg_cmds = None
        self.chat_thread_id = None
        self.subproc = None
        self.thumb = None
        self.excluded_extensions = []
        self.files_to_proceed = []
        self.is_super_chat = self.message.chat.type.name in ["SUPERGROUP", "CHANNEL"]

        self.yt_privacy = None
        self.yt_mode = "playlist"
        self.yt_tags = None
        self.yt_category = None
        self.yt_description = None
        self.yt_playlist_id = None

    def get_token_path(self, dest):
        if dest.startswith("mtp:"):
            return f"tokens/{self.user_id}.pickle"
        if dest.startswith("sa:") or (
            Config.USE_SERVICE_ACCOUNTS and not dest.startswith("tp:")
        ):
            return "accounts"
        return "token.pickle"

    def get_config_path(self, dest):
        return (
            f"rclone/{self.user_id}.conf"
            if dest.startswith("mrcc:")
            else "rclone.conf"
        )

    async def is_token_exists(self, path, status):
        """Checks if Rclone config or GDrive token exists for the given path and operation status."""
        if is_rclone_path(path):
            config_path = self.get_config_path(path)
            if config_path != "rclone.conf" and status == "up":
                self.private_link = True
            if not await aiopath.exists(config_path):
                raise ValueError(f"Rclone Config: {config_path} does not exist!")
        elif (status == "dl" and is_gdrive_link(path)) or (
            status == "up" and is_gdrive_id(path)
        ):
            token_path = self.get_token_path(path)
            if token_path.startswith("tokens/") and status == "up":
                self.private_link = True
            if not await aiopath.exists(token_path):
                raise ValueError(f"Token not found! {token_path} does not exist!")

    async def before_start(self):
        """Performs pre-task setup including:
        - Name substitution, metadata, watermark settings.
        - Excluded extensions.
        - Rclone flags.
        - Path validation and token checks for links and upload destinations.
        - User transmission and hybrid leech settings.
        - FFmpeg command processing.
        - Leech specific settings like split size and document type.
        """
        self.name_sub = (
            self.name_sub
            or self.user_dict.get("NAME_SUBSTITUTE", False)
            or (
                Config.NAME_SUBSTITUTE
                if "NAME_SUBSTITUTE" not in self.user_dict
                else ""
            )
        )
        self.metadata = (
            self.metadata
            or self.user_dict.get("METADATA_KEY", False)
            or (Config.METADATA_KEY if "METADATA_KEY" not in self.user_dict else "")
        )
        self.watermark = (
            self.watermark
            or self.user_dict.get("WATERMARK_KEY", False)
            or (
                Config.WATERMARK_KEY if "WATERMARK_KEY" not in self.user_dict else ""
            )
        )
        if self.name_sub:
            self.name_sub = [x.split("/") for x in self.name_sub.split(" | ")]
        self.excluded_extensions = self.user_dict.get("EXCLUDED_EXTENSIONS") or (
            excluded_extensions
            if "EXCLUDED_EXTENSIONS" not in self.user_dict
            else ["aria2", "!qB"]
        )
        if not self.rc_flags:
            if self.user_dict.get("RCLONE_FLAGS"):
                self.rc_flags = self.user_dict["RCLONE_FLAGS"]
            elif "RCLONE_FLAGS" not in self.user_dict and Config.RCLONE_FLAGS:
                self.rc_flags = Config.RCLONE_FLAGS
        if self.link not in ["rcl", "gdl"]:
            if not self.is_jd:
                if is_rclone_path(self.link):
                    if not self.link.startswith("mrcc:") and self.user_dict.get(
                        "USER_TOKENS",
                        False,
                    ):
                        self.link = f"mrcc:{self.link}"
                    await self.is_token_exists(self.link, "dl")
            elif is_gdrive_link(self.link):
                if not self.link.startswith(
                    ("mtp:", "tp:", "sa:"),
                ) and self.user_dict.get("USER_TOKENS", False):
                    self.link = f"mtp:{self.link}"
                await self.is_token_exists(self.link, "dl")
        elif self.link == "rcl":
            if not self.is_ytdlp and not self.is_jd:
                self.link = await RcloneList(self).get_rclone_path("rcd")
                if not is_rclone_path(self.link):
                    raise ValueError(self.link)
        elif self.link == "gdl" and not self.is_ytdlp and not self.is_jd:
            self.link = await GoogleDriveList(self).get_target_id("gdd")
            if not is_gdrive_id(self.link):
                raise ValueError(self.link)

        self.user_transmission = TgClient.IS_PREMIUM_USER and (
            self.user_dict.get("USER_TRANSMISSION")
            or (
                Config.USER_TRANSMISSION
                and "USER_TRANSMISSION" not in self.user_dict
            )
        )

        if self.user_dict.get("UPLOAD_PATHS", False):
            if self.up_dest in self.user_dict["UPLOAD_PATHS"]:
                self.up_dest = self.user_dict["UPLOAD_PATHS"][self.up_dest]
        elif (
            "UPLOAD_PATHS" not in self.user_dict
            and Config.UPLOAD_PATHS
            and self.up_dest in Config.UPLOAD_PATHS
        ):
            self.up_dest = Config.UPLOAD_PATHS[self.up_dest]

        if self.ffmpeg_cmds and not isinstance(self.ffmpeg_cmds, list):
            if self.user_dict.get("FFMPEG_CMDS", None):
                ffmpeg_dict = deepcopy(self.user_dict["FFMPEG_CMDS"])
            elif "FFMPEG_CMDS" not in self.user_dict and Config.FFMPEG_CMDS:
                ffmpeg_dict = deepcopy(Config.FFMPEG_CMDS)
            else:
                ffmpeg_dict = None
            if ffmpeg_dict is None:
                self.ffmpeg_cmds = ffmpeg_dict
            else:
                cmds = []
                for key in list(self.ffmpeg_cmds):
                    if isinstance(key, tuple):
                        cmds.extend(list(key))
                    elif key in ffmpeg_dict:
                        for ind, vl in enumerate(ffmpeg_dict[key]):
                            if variables := set(findall(r"\{(.*?)\}", vl)):
                                ff_values = (
                                    self.user_dict.get("FFMPEG_VARIABLES", {})
                                    .get(key, {})
                                    .get(str(ind), {})
                                )
                                if Counter(list(variables)) == Counter(
                                    list(ff_values.keys())
                                ):
                                    cmds.append(vl.format(**ff_values))
                            else:
                                cmds.append(vl)
                self.ffmpeg_cmds = cmds
        if not self.is_leech:
            self.stop_duplicate = self.user_dict.get("STOP_DUPLICATE") or (
                "STOP_DUPLICATE" not in self.user_dict and Config.STOP_DUPLICATE
            )
            default_upload = (
                self.user_dict.get("DEFAULT_UPLOAD", "") or Config.DEFAULT_UPLOAD
            )

            if (not self.up_dest and default_upload == "rc") or self.up_dest == "rc":
                self.up_dest = (
                    self.user_dict.get("RCLONE_PATH") or Config.RCLONE_PATH
                )
            elif (
                not self.up_dest and default_upload == "gd"
            ) or self.up_dest == "gd":
                self.up_dest = self.user_dict.get("GDRIVE_ID") or Config.GDRIVE_ID
            elif (not self.up_dest and default_upload == "gofile") or self.up_dest in ["gofile", "gf"]:
                self.up_dest = "gofile"

            chosen_service = ""
            if self.up_dest == "yt" or (
                self.up_dest and self.up_dest.startswith("yt:")
            ):
                chosen_service = "yt"
                self.resolve_youtube_settings()
            else:
                chosen_service = default_upload

            if chosen_service not in ["yt", "gofile"] and not self.up_dest:
                raise ValueError(
                    f"No Upload Destination path/ID for service '{chosen_service}'! Please set an upload path or a default for it."
                )
            elif self.up_dest == "gofile":
                user_token = self.user_dict.get("GOFILE_TOKEN")
                if not user_token and not Config.GOFILE_API:
                    raise ValueError("GoFile API token not configured! Please set your GoFile token in user settings or configure a global token.")
            if is_gdrive_id(self.up_dest):
                if not self.up_dest.startswith(
                    ("mtp:", "tp:", "sa:"),
                ) and self.user_dict.get("USER_TOKENS", False):
                    self.up_dest = f"mtp:{self.up_dest}"
            elif is_rclone_path(self.up_dest):
                if not self.up_dest.startswith("mrcc:") and self.user_dict.get(
                    "USER_TOKENS",
                    False,
                ):
                    self.up_dest = f"mrcc:{self.up_dest}"
                self.up_dest = self.up_dest.strip("/")

            if self.up_dest not in ["rcl", "gdl"]:
                await self.is_token_exists(self.up_dest, "up")

            if self.up_dest == "rcl":
                if self.is_clone:
                    if not is_rclone_path(self.link):
                        raise ValueError(
                            "You can't clone from different types of tools",
                        )
                    config_path = self.get_config_path(self.link)
                else:
                    config_path = None
                self.up_dest = await RcloneList(self).get_rclone_path(
                    "rcu",
                    config_path,
                )
                if not is_rclone_path(self.up_dest):
                    raise ValueError(self.up_dest)
            elif self.up_dest == "gdl":
                if self.is_clone:
                    if not is_gdrive_link(self.link):
                        raise ValueError(
                            "You can't clone from different types of tools",
                        )
                    token_path = self.get_token_path(self.link)
                else:
                    token_path = None
                self.up_dest = await GoogleDriveList(self).get_target_id(
                    "gdu",
                    token_path,
                )
                if not is_gdrive_id(self.up_dest):
                    raise ValueError(self.up_dest)

            elif self.is_clone:
                if is_gdrive_link(self.link) and self.get_token_path(
                    self.link,
                ) != self.get_token_path(self.up_dest):
                    raise ValueError("You must use the same token to clone!")
                if is_rclone_path(self.link) and self.get_config_path(
                    self.link,
                ) != self.get_config_path(self.up_dest):
                    raise ValueError("You must use the same config to clone!")
        else:
            chat = Config.LEECH_DUMP_CHAT
            main_chat = chat[0] if isinstance(chat, list) and chat else chat or ""
            self.up_dest = self.up_dest or main_chat
            self.hybrid_leech = TgClient.IS_PREMIUM_USER and (
                self.user_dict.get("HYBRID_LEECH")
                or (Config.HYBRID_LEECH and "HYBRID_LEECH" not in self.user_dict)
            )
            if self.bot_trans:
                self.user_transmission = False
                self.hybrid_leech = False
            if self.user_trans:
                self.user_transmission = TgClient.IS_PREMIUM_USER
            if self.up_dest:
                if not isinstance(self.up_dest, int):
                    if self.up_dest.startswith("b:"):
                        self.up_dest = self.up_dest.replace("b:", "", 1)
                        self.user_transmission = False
                        self.hybrid_leech = False
                    elif self.up_dest.startswith("u:"):
                        self.up_dest = self.up_dest.replace("u:", "", 1)
                        self.user_transmission = TgClient.IS_PREMIUM_USER
                    elif self.up_dest.startswith("h:"):
                        self.up_dest = self.up_dest.replace("h:", "", 1)
                        self.user_transmission = TgClient.IS_PREMIUM_USER
                        self.hybrid_leech = self.user_transmission
                    if "|" in self.up_dest:
                        self.up_dest, self.chat_thread_id = [
                            int(x) if x.lstrip("-").isdigit() else x
                            for x in self.up_dest.split("|", 1)
                        ]
                    elif self.up_dest.lstrip("-").isdigit():
                        self.up_dest = int(self.up_dest)
                    elif self.up_dest.lower() == "pm":
                        self.up_dest = self.user_id

                if self.user_transmission:
                    try:
                        chat = await TgClient.user.get_chat(self.up_dest)
                    except Exception:
                        chat = None
                    if chat is None:
                        self.user_transmission = False
                        self.hybrid_leech = False
                    else:
                        uploader_id = TgClient.user.me.id
                        if chat.type.name not in ["SUPERGROUP", "CHANNEL", "GROUP"]:
                            self.user_transmission = False
                            self.hybrid_leech = False
                        else:
                            member = await chat.get_member(uploader_id)
                            if (
                                not member.privileges.can_manage_chat
                                or not member.privileges.can_delete_messages
                            ):
                                self.user_transmission = False
                                self.hybrid_leech = False

                if not self.user_transmission or self.hybrid_leech:
                    try:
                        chat = await self.client.get_chat(self.up_dest)
                    except Exception:
                        chat = None
                    if chat is None:
                        if self.user_transmission:
                            self.hybrid_leech = False
                        else:
                            raise ValueError("Chat not found!")
                    else:
                        uploader_id = self.client.me.id
                        if chat.type.name in ["SUPERGROUP", "CHANNEL", "GROUP"]:
                            member = await chat.get_member(uploader_id)
                            if (
                                not member.privileges.can_manage_chat
                                or not member.privileges.can_delete_messages
                            ):
                                if not self.user_transmission:
                                    raise ValueError(
                                        "You don't have enough privileges in this chat!",
                                    )
                                self.hybrid_leech = False
                        else:
                            try:
                                await self.client.send_chat_action(
                                    self.up_dest,
                                    ChatAction.TYPING,
                                )
                            except Exception:
                                raise ValueError(
                                    "Start the bot and try again!",
                                ) from None
            elif (
                self.user_transmission or self.hybrid_leech
            ) and not self.is_super_chat:
                self.user_transmission = False
                self.hybrid_leech = False
            if self.split_size:
                if self.split_size.isdigit():
                    self.split_size = int(self.split_size)
                else:
                    self.split_size = get_size_bytes(self.split_size)
            self.split_size = (
                self.split_size
                or self.user_dict.get("LEECH_SPLIT_SIZE")
                or Config.LEECH_SPLIT_SIZE
            )
            self.max_split_size = (
                TgClient.MAX_SPLIT_SIZE if self.user_transmission else 2097152000
            )
            self.split_size = min(self.split_size, self.max_split_size)

            if not self.as_doc:
                self.as_doc = (
                    not self.as_med
                    if self.as_med
                    else (
                        self.user_dict.get("AS_DOCUMENT", False)
                        or (
                            Config.AS_DOCUMENT
                            and "AS_DOCUMENT" not in self.user_dict
                        )
                    )
                )

            self.thumbnail_layout = (
                self.thumbnail_layout
                or self.user_dict.get("THUMBNAIL_LAYOUT", False)
                or (
                    Config.THUMBNAIL_LAYOUT
                    if "THUMBNAIL_LAYOUT" not in self.user_dict
                    else ""
                )
            )

            if self.thumb != "none" and is_telegram_link(self.thumb):
                msg, _ = (await get_tg_link_message(self.thumb))[0]
                self.thumb = (
                    await create_thumb(msg) if msg.photo or msg.document else ""
                )

    def resolve_youtube_settings(self):
        def get_cleaned_value(value, default, allowed=None, to_lower=False):
            val = value if value is not None else self.user_dict.get(default)
            if val:
                val = val.strip()
                if to_lower:
                    val = val.lower()
                if not allowed or val in allowed:
                    return val
            return None

        self.yt_privacy = (
            get_cleaned_value(
                self.yt_privacy,
                "YT_DEFAULT_PRIVACY",
                allowed=["private", "public", "unlisted"],
                to_lower=True,
            )
            or self.yt_privacy
        )
        if not self.yt_privacy:
            self.yt_privacy = "unlisted"

        self.yt_mode = (
            get_cleaned_value(
                self.yt_mode,
                "YT_DEFAULT_FOLDER_MODE",
                allowed=["playlist", "individual", "playlist_and_individual"],
            )
            or self.yt_mode
        )
        if not self.yt_mode:
            self.yt_mode = "playlist"

        tags_str = (
            self.yt_tags
            if self.yt_tags is not None
            else self.user_dict.get("YT_DEFAULT_TAGS")
        )
        if tags_str is not None:
            tags_str = tags_str.strip()
            if tags_str.lower() == "none":
                self.yt_tags = []
            else:
                self.yt_tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        self.yt_category = (
            get_cleaned_value(self.yt_category, "YT_DEFAULT_CATEGORY", allowed=None)
            if (
                get_cleaned_value(
                    self.yt_category,
                    "YT_DEFAULT_CATEGORY",
                    allowed=None,
                    to_lower=False,
                )
                or ""
            ).isdigit()
            else self.yt_category
        )

        description = (
            self.yt_description
            if self.yt_description is not None
            else self.user_dict.get("YT_DEFAULT_DESCRIPTION")
        )
        self.yt_description = (
            description.strip() if description is not None else self.yt_description
        )

        if self.yt_playlist_id and self.yt_playlist_id.strip():
            self.yt_playlist_id = self.yt_playlist_id.strip()

    async def get_tag(self, text: list):
        if len(text) > 1 and text[1].startswith("Tag: "):
            user_info = text[1].split("Tag: ")
            if len(user_info) >= 3:
                id_ = user_info[-1]
                self.tag = " ".join(user_info[:-1])
            else:
                self.tag, id_ = text[1].split("Tag: ")[1].split()
            self.user = self.message.from_user = await self.client.get_users(id_)
            self.user_id = self.user.id
            self.user_dict = user_data.get(self.user_id, {})
            with contextlib.suppress(Exception):
                await self.message.unpin()
        if self.user:
            if username := self.user.username:
                self.tag = f"@{username}"
            elif hasattr(self.user, "mention"):
                self.tag = self.user.mention
            else:
                self.tag = self.user.title

    @new_task
    async def run_multi(self, input_list, obj):
        await sleep(7)
        if not self.multi_tag and self.multi > 1:
            self.multi_tag = token_hex(2)
            multi_tags.add(self.multi_tag)
        elif self.multi <= 1:
            if self.multi_tag in multi_tags:
                multi_tags.discard(self.multi_tag)
            return
        if self.multi_tag and self.multi_tag not in multi_tags:
            await send_message(
                self.message,
                f"{self.tag} Multi-task has been cancelled!",
            )
            await send_status_message(self.message)
            async with task_dict_lock:
                for fd_name in self.same_dir:
                    self.same_dir[fd_name]["total"] -= self.multi
            return
        if len(self.bulk) != 0:
            msg = input_list[:1]
            msg.append(f"{self.bulk[0]} -i {self.multi - 1} {self.options}")
            msgts = " ".join(msg)
            if self.multi > 2:
                msgts += f"\nCancel Multi: <code>/stop {self.multi_tag}</code>"
            nextmsg = await send_message(self.message, msgts)
        else:
            msg = [s.strip() for s in input_list]
            index = msg.index("-i")
            msg[index + 1] = f"{self.multi - 1}"
            nextmsg = await self.client.get_messages(
                chat_id=self.message.chat.id,
                message_ids=self.message.reply_to_message_id + 1,
            )
            msgts = " ".join(msg)
            if self.multi > 2:
                msgts += f"\nCancel Multi: <code>/stop {self.multi_tag}</code>"
            nextmsg = await send_message(nextmsg, msgts)
        nextmsg = await self.client.get_messages(
            chat_id=self.message.chat.id,
            message_ids=nextmsg.id,
        )
        if self.message.from_user:
            nextmsg.from_user = self.user
        else:
            nextmsg.sender_chat = self.user
        if intervals["stopAll"]:
            return
        await obj(
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

    async def init_bulk(self, input_list, bulk_start, bulk_end, obj):
        try:
            self.bulk = await extract_bulk_links(self.message, bulk_start, bulk_end)
            if len(self.bulk) == 0:
                raise ValueError("Bulk Empty!")
            b_msg = input_list[:1]
            self.options = input_list[1:]
            index = self.options.index("-b")
            del self.options[index]
            if bulk_start or bulk_end:
                del self.options[index + 1]
            self.options = " ".join(self.options)
            b_msg.append(f"{self.bulk[0]} -i {len(self.bulk)} {self.options}")
            msg = " ".join(b_msg)
            if len(self.bulk) > 2:
                self.multi_tag = token_hex(2)
                multi_tags.add(self.multi_tag)
                msg += f"\nCancel Multi: <code>/stop {self.multi_tag}</code>"
            nextmsg = await send_message(self.message, msg)
            nextmsg = await self.client.get_messages(
                chat_id=self.message.chat.id,
                message_ids=nextmsg.id,
            )
            if self.message.from_user:
                nextmsg.from_user = self.user
            else:
                nextmsg.sender_chat = self.user
            await obj(
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
        except Exception as e:
            await send_message(
                self.message,
                f"Reply to a text file or a Telegram message with links separated by new lines. Error: {e}",
            )

    async def proceed_extract(self, dl_path, gid):
        """Extracts archives from the downloaded path."""
        pswd = self.extract if isinstance(self.extract, str) else ""
        self.files_to_proceed = []
        if self.is_file and is_archive(dl_path):
            self.files_to_proceed.append(dl_path)
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    if is_first_archive_split(file_) or (
                        is_archive(file_)
                        and not file_.strip().lower().endswith(".rar")
                    ):
                        f_path = ospath.join(dirpath, file_)
                        self.files_to_proceed.append(f_path)

        if not self.files_to_proceed:
            return dl_path
        t_path = dl_path
        sevenz = SevenZ(self)
        LOGGER.info(f"Extracting: {self.name}")
        async with task_dict_lock:
            task_dict[self.mid] = SevenZStatus(self, sevenz, gid, "Extract")
        for dirpath, _, files in await sync_to_async(
            walk,
            self.up_dir or self.dir,
            topdown=False,
        ):
            for file_ in files:
                if self.is_cancelled:
                    return False
                if is_first_archive_split(file_) or (
                    is_archive(file_) and not file_.strip().lower().endswith(".rar")
                ):
                    self.proceed_count += 1
                    f_path = ospath.join(dirpath, file_)
                    t_path = get_base_name(f_path) if self.is_file else dirpath
                    if not self.is_file:
                        self.subname = file_
                    code = await sevenz.extract(f_path, t_path, pswd)
                else:
                    code = 0
            if self.is_cancelled:
                return code
            if code == 0:
                for file_ in files:
                    if is_archive_split(file_) or is_archive(file_):
                        del_path = ospath.join(dirpath, file_)
                        try:
                            await remove(del_path)
                        except Exception:
                            self.is_cancelled = True
        if self.proceed_count == 0:
            LOGGER.info("No extractable files found!")
        return t_path if self.is_file and code == 0 else dl_path

    async def proceed_ffmpeg(self, dl_path, gid):
        """Processes media files using FFmpeg commands defined in the task."""
        checked = False
        inputs = {}
        cmds = [
            [part.strip() for part in split(item) if part.strip()]
            for item in self.ffmpeg_cmds
        ]
        try:
            ffmpeg = FFMpeg(self)
            for ffmpeg_cmd in cmds:
                self.proceed_count = 0
                cmd = [
                    "xtra",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                    "-threads",
                    "4",
                    *ffmpeg_cmd,
                ]
                if "-del" in cmd:
                    cmd.remove("-del")
                    delete_files = True
                else:
                    delete_files = False
                input_indexes = [
                    index for index, value in enumerate(cmd) if value == "-i"
                ]
                for index in input_indexes:
                    if cmd[index + 1].startswith("mltb"):
                        input_file = cmd[index + 1]
                        break
                if input_file.lower().endswith(".video"):
                    ext = "video"
                elif input_file.lower().endswith(".audio"):
                    ext = "audio"
                elif "." not in input_file:
                    ext = "all"
                else:
                    ext = ospath.splitext(input_file)[-1].lower()
                if await aiopath.isfile(dl_path):
                    is_video, is_audio, _ = await get_document_type(dl_path)
                    if (not is_video and not is_audio) or (
                        is_video and ext == "audio"
                    ):
                        break
                    if (is_audio and not is_video and ext == "video") or (
                        ext
                        not in [
                            "all",
                            "audio",
                            "video",
                        ]
                        and not dl_path.strip().lower().endswith(ext)
                    ):
                        break
                    new_folder = ospath.splitext(dl_path)[0]
                    name = ospath.basename(dl_path)
                    await makedirs(new_folder, exist_ok=True)
                    file_path = f"{new_folder}/{name}"
                    await move(dl_path, file_path)
                    if not checked:
                        checked = True
                        async with task_dict_lock:
                            task_dict[self.mid] = FFmpegStatus(
                                self,
                                ffmpeg,
                                gid,
                                "FFmpeg",
                            )
                        self.progress = False
                        await cpu_eater_lock.acquire()
                        self.progress = True
                    LOGGER.info(f"Running FFmpeg command for: {file_path}")
                    for index in input_indexes:
                        if cmd[index + 1].startswith("mltb"):
                            cmd[index + 1] = file_path
                        elif is_telegram_link(cmd[index + 1]):
                            msg = (await get_tg_link_message(cmd[index + 1]))[0]
                            file_dir = await temp_download(msg)
                            inputs[index + 1] = file_dir
                            cmd[index + 1] = file_dir
                    self.subsize = self.size
                    res = await ffmpeg.ffmpeg_cmds(cmd, file_path)
                    if res:
                        if delete_files:
                            await remove(file_path)
                            if len(await listdir(new_folder)) == 1:
                                folder = new_folder.rsplit("/", 1)[0]
                                self.name = ospath.basename(res[0])
                                if self.name.startswith("ffmpeg"):
                                    self.name = self.name.split(".", 1)[-1]
                                dl_path = ospath.join(folder, self.name)
                                await move(res[0], dl_path)
                                await rmtree(new_folder)
                            else:
                                dl_path = new_folder
                                self.name = new_folder.rsplit("/", 1)[-1]
                        else:
                            dl_path = new_folder
                            self.name = new_folder.rsplit("/", 1)[-1]
                    else:
                        await move(file_path, dl_path)
                        await rmtree(new_folder)
                else:
                    for dirpath, _, files in await sync_to_async(
                        walk,
                        dl_path,
                        topdown=False,
                    ):
                        for file_ in files:
                            var_cmd = cmd.copy()
                            if self.is_cancelled:
                                return False
                            f_path = ospath.join(dirpath, file_)
                            is_video, is_audio, _ = await get_document_type(f_path)
                            if (not is_video and not is_audio) or (
                                is_video and ext == "audio"
                            ):
                                continue
                            if (is_audio and not is_video and ext == "video") or (
                                ext
                                not in [
                                    "all",
                                    "audio",
                                    "video",
                                ]
                                and not f_path.strip().lower().endswith(ext)
                            ):
                                continue
                            self.proceed_count += 1
                            var_cmd[index + 1] = f_path
                            if not checked:
                                checked = True
                                async with task_dict_lock:
                                    task_dict[self.mid] = FFmpegStatus(
                                        self,
                                        ffmpeg,
                                        gid,
                                        "FFmpeg",
                                    )
                                self.progress = False
                                await cpu_eater_lock.acquire()
                                self.progress = True
                            LOGGER.info(f"Running FFmpeg command for: {f_path}")
                            self.subsize = await get_path_size(f_path)
                            self.subname = file_
                            res = await ffmpeg.ffmpeg_cmds(var_cmd, f_path)
                            if res and delete_files:
                                await remove(f_path)
                                if len(res) == 1:
                                    file_name = ospath.basename(res[0])
                                    if file_name.startswith("ffmpeg"):
                                        newname = file_name.split(".", 1)[-1]
                                        newres = ospath.join(dirpath, newname)
                                        await move(res[0], newres)
                for inp in inputs.values():
                    if "/temp/" in inp and aiopath.exists(inp):
                        await remove(inp)
        finally:
            if checked:
                cpu_eater_lock.release()
        return dl_path

    async def substitute(self, dl_path):
        """Performs name substitution on downloaded files/folders based on task settings."""

        def perform_substitution(name, substitutions):
            for substitution in substitutions:
                sen = False
                pattern = substitution[0]
                if len(substitution) > 1:
                    if len(substitution) > 2:
                        sen = substitution[2] == "s"
                        res = substitution[1]
                    elif len(substitution[1]) == 0:
                        res = " "
                    else:
                        res = substitution[1]
                else:
                    res = ""
                try:
                    name = sub(
                        rf"{pattern}",
                        res,
                        name,
                        flags=IGNORECASE if sen else 0,
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Substitute Error: pattern: {pattern} res: {res}. Error: {e}",
                    )
                    return False
                if len(name.encode()) > 255:
                    LOGGER.error(f"Substitute: {name} is too long")
                    return False
            return name

        if self.is_file:
            up_dir, name = dl_path.rsplit("/", 1)
            new_name = perform_substitution(name, self.name_sub)
            if not new_name:
                return dl_path
            new_path = ospath.join(up_dir, new_name)
            with contextlib.suppress(Exception):
                await move(dl_path, new_path)
            return new_path
        for dirpath, _, files in await sync_to_async(walk, dl_path, topdown=False):
            for file_ in files:
                f_path = ospath.join(dirpath, file_)
                new_name = perform_substitution(file_, self.name_sub)
                if not new_name:
                    continue
                with contextlib.suppress(Exception):
                    await move(f_path, ospath.join(dirpath, new_name))
        return dl_path

    async def remove_www_prefix(self, dl_path):
        """Removes 'www.domain.com - ' like prefixes from filenames."""

        def clean_filename(name):
            return sub(
                r"^www\.[^ ]+\s*-\s*|\s*^www\.[^ ]+\s*",
                "",
                name,
                flags=IGNORECASE,
            ).lstrip()

        if self.is_file:
            up_dir, name = dl_path.rsplit("/", 1)
            new_name = clean_filename(name)
            if new_name == name:
                return dl_path
            new_path = ospath.join(up_dir, new_name)
            with contextlib.suppress(Exception):
                await move(dl_path, new_path)
            return new_path

        for dirpath, _, files in await sync_to_async(walk, dl_path, topdown=False):
            for file_ in files:
                f_path = ospath.join(dirpath, file_)
                new_name = clean_filename(file_)
                if new_name == file_:
                    continue
                with contextlib.suppress(Exception):
                    await move(f_path, ospath.join(dirpath, new_name))

        return dl_path

    async def generate_screenshots(self, dl_path):
        """Generates screenshots for video files."""
        ss_nb = int(self.screen_shots) if isinstance(self.screen_shots, str) else 10
        if self.is_file:
            if (await get_document_type(dl_path))[0]:
                LOGGER.info(f"Creating Screenshot for: {dl_path}")
                res = await take_ss(dl_path, ss_nb)
                if res:
                    new_folder = ospath.splitext(dl_path)[0]
                    name = ospath.basename(dl_path)
                    await makedirs(new_folder, exist_ok=True)
                    await gather(
                        move(dl_path, f"{new_folder}/{name}"),
                        move(res, new_folder),
                    )
                    return new_folder
        else:
            LOGGER.info(f"Creating Screenshot for: {dl_path}")
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    f_path = ospath.join(dirpath, file_)
                    if (await get_document_type(f_path))[0]:
                        await take_ss(f_path, ss_nb)
        return dl_path

    async def convert_media(self, dl_path, gid):
        """Converts video/audio files to specified formats based on task settings."""
        fvext = []
        if self.convert_video:
            vdata = self.convert_video.split()
            vext = vdata[0].lower()
            if len(vdata) > 2:
                if "+" in vdata[1].split():
                    vstatus = "+"
                elif "-" in vdata[1].split():
                    vstatus = "-"
                else:
                    vstatus = ""
                fvext.extend(f".{ext.lower()}" for ext in vdata[2:])
            else:
                vstatus = ""
        else:
            vext = ""
            vstatus = ""

        faext = []
        if self.convert_audio:
            adata = self.convert_audio.split()
            aext = adata[0].lower()
            if len(adata) > 2:
                if "+" in adata[1].split():
                    astatus = "+"
                elif "-" in adata[1].split():
                    astatus = "-"
                else:
                    astatus = ""
                faext.extend(f".{ext.lower()}" for ext in adata[2:])
            else:
                astatus = ""
        else:
            aext = ""
            astatus = ""

        self.files_to_proceed = {}
        all_files = []
        if self.is_file:
            all_files.append(dl_path)
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    f_path = ospath.join(dirpath, file_)
                    all_files.append(f_path)

        for f_path in all_files:
            is_video, is_audio, _ = await get_document_type(f_path)
            if (
                is_video
                and vext
                and not f_path.strip().lower().endswith(f".{vext}")
                and (
                    (
                        vstatus == "+"
                        and f_path.strip().lower().endswith(tuple(fvext))
                    )
                    or (
                        vstatus == "-"
                        and not f_path.strip().lower().endswith(tuple(fvext))
                    )
                    or not vstatus
                )
            ):
                self.files_to_proceed[f_path] = "video"
            elif (
                is_audio
                and aext
                and not is_video
                and not f_path.strip().lower().endswith(f".{aext}")
                and (
                    (
                        astatus == "+"
                        and f_path.strip().lower().endswith(tuple(faext))
                    )
                    or (
                        astatus == "-"
                        and not f_path.strip().lower().endswith(tuple(faext))
                    )
                    or not astatus
                )
            ):
                self.files_to_proceed[f_path] = "audio"
        del all_files

        if self.files_to_proceed:
            ffmpeg = FFMpeg(self)
            async with task_dict_lock:
                task_dict[self.mid] = FFmpegStatus(self, ffmpeg, gid, "Convert")
            self.progress = False
            async with cpu_eater_lock:
                self.progress = True
                for f_path, f_type in self.files_to_proceed.items():
                    self.proceed_count += 1
                    LOGGER.info(f"Converting: {f_path}")
                    if self.is_file:
                        self.subsize = self.size
                    else:
                        self.subsize = await get_path_size(f_path)
                        self.subname = ospath.basename(f_path)
                    if f_type == "video":
                        res = await ffmpeg.convert_video(f_path, vext)
                    else:
                        res = await ffmpeg.convert_audio(f_path, aext)
                    if res:
                        try:
                            await remove(f_path)
                        except Exception:
                            self.is_cancelled = True
                            return False
                        if self.is_file:
                            return res
        return dl_path

    async def generate_sample_video(self, dl_path, gid):
        """Generates a sample video from the input file."""
        data = (
            self.sample_video.split(":")
            if isinstance(self.sample_video, str)
            else ""
        )
        if data:
            sample_duration = int(data[0]) if data[0] else 60
            part_duration = int(data[1]) if len(data) > 1 else 4
        else:
            sample_duration = 60
            part_duration = 4

        self.files_to_proceed = {}
        if self.is_file and (await get_document_type(dl_path))[0]:
            file_ = ospath.basename(dl_path)
            self.files_to_proceed[dl_path] = file_
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    f_path = ospath.join(dirpath, file_)
                    if (await get_document_type(f_path))[0]:
                        self.files_to_proceed[f_path] = file_
        if self.files_to_proceed:
            ffmpeg = FFMpeg(self)
            async with task_dict_lock:
                task_dict[self.mid] = FFmpegStatus(self, ffmpeg, gid, "Sample Video")
            self.progress = False
            async with cpu_eater_lock:
                self.progress = True
                LOGGER.info(f"Creating sample video for: {self.name}")
                for f_path, file_ in self.files_to_proceed.items():
                    self.proceed_count += 1
                    if self.is_file:
                        self.subsize = self.size
                    else:
                        self.subsize = await get_path_size(f_path)
                        self.subname = file_
                    res = await ffmpeg.sample_video(
                        f_path,
                        sample_duration,
                        part_duration,
                    )
                    if res and self.is_file:
                        new_folder = ospath.splitext(f_path)[0]
                        await makedirs(new_folder, exist_ok=True)
                        await gather(
                            move(f_path, f"{new_folder}/{file_}"),
                            move(res, f"{new_folder}/SAMPLE.{file_}"),
                        )
                        return new_folder
        return dl_path

    async def proceed_compress(self, dl_path, gid):
        """Compresses the downloaded file/folder into a zip archive."""
        pswd = self.compress if isinstance(self.compress, str) else ""
        if self.is_leech and self.is_file:
            new_folder = ospath.splitext(dl_path)[0]
            name = ospath.basename(dl_path)
            await makedirs(new_folder, exist_ok=True)
            new_dl_path = f"{new_folder}/{name}"
            await move(dl_path, new_dl_path)
            dl_path = new_dl_path
            up_path = f"{new_dl_path}.zip"
            self.is_file = False
        else:
            up_path = f"{dl_path}.zip"
        sevenz = SevenZ(self)
        async with task_dict_lock:
            task_dict[self.mid] = SevenZStatus(self, sevenz, gid, "Zip")
        return await sevenz.zip(dl_path, up_path, pswd)

    async def proceed_split(self, dl_path, gid):
        """Splits files larger than the specified split size."""
        self.files_to_proceed = {}
        if self.is_file:
            f_size = await get_path_size(dl_path)
            if f_size > self.split_size:
                self.files_to_proceed[dl_path] = [f_size, ospath.basename(dl_path)]
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    f_path = ospath.join(dirpath, file_)
                    f_size = await get_path_size(f_path)
                    if f_size > self.split_size:
                        self.files_to_proceed[f_path] = [f_size, file_]
        if self.files_to_proceed:
            ffmpeg = FFMpeg(self)
            async with task_dict_lock:
                task_dict[self.mid] = FFmpegStatus(self, ffmpeg, gid, "Split")
            LOGGER.info(f"Splitting: {self.name}")
            for f_path, (f_size, file_) in self.files_to_proceed.items():
                self.proceed_count += 1
                if self.is_file:
                    self.subsize = self.size
                else:
                    self.subsize = f_size
                    self.subname = file_
                parts = -(-f_size // self.split_size)
                split_size = self.split_size
                if not self.as_doc and (await get_document_type(f_path))[0]:
                    self.progress = True
                    res = await ffmpeg.split(f_path, file_, parts, split_size)
                else:
                    self.progress = False
                    res = await split_file(f_path, split_size, self)
                if self.is_cancelled:
                    return False
                if res or f_size >= self.max_split_size:
                    try:
                        await remove(f_path)
                    except Exception:
                        self.is_cancelled = True
            return None
        return None

    async def proceed_metadata(self, dl_path, gid):
        """Adds metadata to MKV files based on the task's metadata key."""
        key = self.metadata
        ffmpeg = FFMpeg(self)
        checked = False
        if self.is_file:
            if is_mkv(dl_path):
                cmd, temp_file = await get_metadata_cmd(dl_path, key)
                if cmd:
                    if not checked:
                        checked = True
                        async with task_dict_lock:
                            task_dict[self.mid] = FFmpegStatus(
                                self,
                                ffmpeg,
                                gid,
                                "Metadata",
                            )
                        self.progress = False
                        await cpu_eater_lock.acquire()
                        self.progress = True
                    self.subsize = self.size
                    res = await ffmpeg.metadata_watermark_cmds(cmd, dl_path)
                    if res:
                        os.replace(temp_file, dl_path)
                    elif await aiopath.exists(temp_file):
                        os.remove(temp_file)
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    file_path = ospath.join(dirpath, file_)
                    if self.is_cancelled:
                        cpu_eater_lock.release()
                        return ""
                    self.proceed_count += 1
                    if is_mkv(file_path):
                        cmd, temp_file = await get_metadata_cmd(file_path, key)
                        if cmd:
                            if not checked:
                                checked = True
                                async with task_dict_lock:
                                    task_dict[self.mid] = FFmpegStatus(
                                        self,
                                        ffmpeg,
                                        gid,
                                        "Metadata",
                                    )
                                self.progress = False
                                await cpu_eater_lock.acquire()
                                self.progress = True
                            LOGGER.info(f"Running metadata command for: {file_path}")
                            self.subsize = await aiopath.getsize(file_path)
                            self.subname = file_
                            res = await ffmpeg.metadata_watermark_cmds(
                                cmd,
                                file_path,
                            )
                            if res:
                                os.replace(temp_file, file_path)
                            elif await aiopath.exists(temp_file):
                                os.remove(temp_file)
        if checked:
            cpu_eater_lock.release()
        return dl_path

    async def proceed_watermark(self, dl_path, gid):
        """Adds a text watermark to MKV video files."""
        key = self.watermark
        ffmpeg = FFMpeg(self)
        checked = False
        if self.is_file:
            if is_mkv(dl_path):
                cmd, temp_file = await get_watermark_cmd(dl_path, key)
                if cmd:
                    if not checked:
                        checked = True
                        async with task_dict_lock:
                            task_dict[self.mid] = FFmpegStatus(
                                self,
                                ffmpeg,
                                gid,
                                "Watermark",
                            )
                        self.progress = False
                        await cpu_eater_lock.acquire()
                        self.progress = True
                    self.subsize = self.size
                    res = await ffmpeg.metadata_watermark_cmds(cmd, dl_path)
                    if res:
                        os.replace(temp_file, dl_path)
                    elif await aiopath.exists(temp_file):
                        os.remove(temp_file)
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    file_path = ospath.join(dirpath, file_)
                    if self.is_cancelled:
                        cpu_eater_lock.release()
                        return ""
                    if is_mkv(file_path):
                        cmd, temp_file = await get_watermark_cmd(file_path, key)
                        if cmd:
                            if not checked:
                                checked = True
                                async with task_dict_lock:
                                    task_dict[self.mid] = FFmpegStatus(
                                        self,
                                        ffmpeg,
                                        gid,
                                        "Watermark",
                                    )
                                self.progress = False
                                await cpu_eater_lock.acquire()
                                self.progress = True
                            LOGGER.info(
                                f"Running watermark command for: {file_path}"
                            )
                            self.subsize = await aiopath.getsize(file_path)
                            self.subname = file_
                            res = await ffmpeg.metadata_watermark_cmds(
                                cmd,
                                file_path,
                            )
                            if res:
                                os.replace(temp_file, file_path)
                            elif await aiopath.exists(temp_file):
                                os.remove(temp_file)
        if checked:
            cpu_eater_lock.release()
        return dl_path

    async def proceed_embed_thumb(self, dl_path, gid):
        """Embeds a thumbnail into MKV video files."""
        thumb = self.e_thumb
        ffmpeg = FFMpeg(self)
        checked = False
        if self.is_file:
            if is_mkv(dl_path):
                cmd, temp_file = await get_embed_thumb_cmd(dl_path, thumb)
                if cmd:
                    if not checked:
                        checked = True
                        async with task_dict_lock:
                            task_dict[self.mid] = FFmpegStatus(
                                self,
                                ffmpeg,
                                gid,
                                "E_thumb",
                            )
                        self.progress = False
                        await cpu_eater_lock.acquire()
                        self.progress = True
                    self.subsize = self.size
                    res = await ffmpeg.metadata_watermark_cmds(cmd, dl_path)
                    if res:
                        os.replace(temp_file, dl_path)
                    elif await aiopath.exists(temp_file):
                        os.remove(temp_file)
        else:
            for dirpath, _, files in await sync_to_async(
                walk,
                dl_path,
                topdown=False,
            ):
                for file_ in files:
                    file_path = ospath.join(dirpath, file_)
                    if self.is_cancelled:
                        cpu_eater_lock.release()
                        return ""
                    if is_mkv(file_path):
                        cmd, temp_file = await get_embed_thumb_cmd(file_path, thumb)
                        if cmd:
                            if not checked:
                                checked = True
                                async with task_dict_lock:
                                    task_dict[self.mid] = FFmpegStatus(
                                        self,
                                        ffmpeg,
                                        gid,
                                        "E_thumb",
                                    )
                                self.progress = False
                                await cpu_eater_lock.acquire()
                                self.progress = True
                            LOGGER.info(f"Running cmd for: {file_path}")
                            self.subsize = await aiopath.getsize(file_path)
                            self.subname = file_
                            res = await ffmpeg.metadata_watermark_cmds(
                                cmd,
                                file_path,
                            )
                            if res:
                                os.replace(temp_file, file_path)
                            elif await aiopath.exists(temp_file):
                                os.remove(temp_file)
        if checked:
            cpu_eater_lock.release()
        return dl_path
