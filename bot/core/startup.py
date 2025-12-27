from asyncio import create_subprocess_exec, create_subprocess_shell, sleep
from os import environ

import aiohttp
from aiofiles import open as aiopen
from aiofiles.os import makedirs, remove
from aiofiles.os import path as aiopath
from aioshutil import rmtree

from bot import (
    LOGGER,
    aria2_options,
    auth_chats,
    drives_ids,
    drives_names,
    excluded_extensions,
    included_extensions,
    index_urls,
    nzb_options,
    qbit_options,
    rss_dict,
    sabnzbd_client,
    shorteners_list,
    sudo_users,
    user_data,
)
from bot.helper.ext_utils.db_handler import database

from .config_manager import Config
from .telegram_manager import TgClient
from .torrent_manager import TorrentManager


async def update_qb_options():
    """Updates qBittorrent options either from current preferences or saved configuration."""
    LOGGER.info("Get qBittorrent options from server")
    if not qbit_options:
        opt = await TorrentManager.qbittorrent.app.preferences()
        qbit_options.update(opt)
        del qbit_options["listen_port"]
        for k in list(qbit_options.keys()):
            if k.startswith("rss"):
                del qbit_options[k]
        qbit_options["web_ui_password"] = "mltbmltb"
        await TorrentManager.qbittorrent.app.set_preferences(
            {"web_ui_password": "mltbmltb"},
        )
    else:
        await TorrentManager.qbittorrent.app.set_preferences(qbit_options)


async def update_aria2_options():
    """Updates Aria2c global options either from current settings or saved configuration."""
    LOGGER.info("Get aria2 options from server")
    if not aria2_options:
        op = await TorrentManager.aria2.getGlobalOption()
        aria2_options.update(op)
    else:
        await TorrentManager.aria2.changeGlobalOption(aria2_options)


async def update_nzb_options():
    """Updates NZB options from Sabnzbd client configuration."""
    LOGGER.info("Get SABnzbd options from server")
    while True:
        try:
            no = (await sabnzbd_client.get_config())["config"]["misc"]
            nzb_options.update(no)
        except Exception:
            await sleep(0.5)
            continue
        break


async def load_settings():
    """Loads bot settings from the database (if DATABASE_URL is set)
    and applies them to the current runtime configuration.
    This includes deployment configs, general configs, private files,
    and user-specific data like thumbnails and rclone configs.
    """
    if not Config.DATABASE_URL:
        return
    for p in ["thumbnails", "tokens", "rclone"]:
        if await aiopath.exists(p):
            await rmtree(p, ignore_errors=True)
    await database.connect()
    if database.db is not None:
        BOT_ID = Config.BOT_TOKEN.split(":", 1)[0]
        current_deploy_config = Config.get_all()
        old_deploy_config = await database.db.settings.deployConfig.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        )

        if old_deploy_config is None:
            await database.db.settings.deployConfig.replace_one(
                {"_id": BOT_ID},
                current_deploy_config,
                upsert=True,
            )
        elif old_deploy_config != current_deploy_config:
            runtime_config = (
                await database.db.settings.config.find_one(
                    {"_id": BOT_ID},
                    {"_id": 0},
                )
                or {}
            )

            new_vars = {
                k: v
                for k, v in current_deploy_config.items()
                if k not in runtime_config
            }
            if new_vars:
                runtime_config.update(new_vars)
                await database.db.settings.config.replace_one(
                    {"_id": BOT_ID},
                    runtime_config,
                    upsert=True,
                )
                LOGGER.info(f"Added new variables: {list(new_vars.keys())}")

            await database.db.settings.deployConfig.replace_one(
                {"_id": BOT_ID},
                current_deploy_config,
                upsert=True,
            )

        runtime_config = await database.db.settings.config.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        )
        if runtime_config:
            Config.load_dict(runtime_config)

        if pf_dict := await database.db.settings.files.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        ):
            for key, value in pf_dict.items():
                if value:
                    file_ = key.replace("__", ".")
                    async with aiopen(file_, "wb+") as f:
                        await f.write(value)

        if a2c_options := await database.db.settings.aria2c.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        ):
            aria2_options.update(a2c_options)

        if qbit_opt := await database.db.settings.qbittorrent.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        ):
            qbit_options.update(qbit_opt)

        if nzb_opt := await database.db.settings.nzb.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        ):
            if await aiopath.exists("sabnzbd/SABnzbd.ini.bak"):
                await remove("sabnzbd/SABnzbd.ini.bak")
            ((key, value),) = nzb_opt.items()
            file_ = key.replace("__", ".")
            async with aiopen(f"sabnzbd/{file_}", "wb+") as f:
                await f.write(value)

        if await database.db.users.find_one():
            for p in ["thumbnails", "tokens", "rclone"]:
                if not await aiopath.exists(p):
                    await makedirs(p)
            rows = database.db.users.find({})
            async for row in rows:
                uid = row["_id"]
                del row["_id"]
                thumb_path = f"thumbnails/{uid}.jpg"
                rclone_config_path = f"rclone/{uid}.conf"
                token_path = f"tokens/{uid}.pickle"
                if row.get("THUMBNAIL"):
                    async with aiopen(thumb_path, "wb+") as f:
                        await f.write(row["THUMBNAIL"])
                    row["THUMBNAIL"] = thumb_path
                if row.get("RCLONE_CONFIG"):
                    async with aiopen(rclone_config_path, "wb+") as f:
                        await f.write(row["RCLONE_CONFIG"])
                    row["RCLONE_CONFIG"] = rclone_config_path
                if row.get("TOKEN_PICKLE"):
                    async with aiopen(token_path, "wb+") as f:
                        await f.write(row["TOKEN_PICKLE"])
                    row["TOKEN_PICKLE"] = token_path
                user_data[uid] = row
            LOGGER.info("User data has been imported from the Database.")

        if await database.db.rss[BOT_ID].find_one():
            rows = database.db.rss[BOT_ID].find({})
            async for row in rows:
                user_id = row["_id"]
                del row["_id"]
                rss_dict[user_id] = row
            LOGGER.info("RSS data has been imported from the Database.")


async def save_settings():
    """Saves the current bot configuration to the database if DATABASE_URL is set."""
    if database.db is None:
        return
    config_dict = Config.get_all()
    await database.db.settings.config.replace_one(
        {"_id": TgClient.ID},
        config_dict,
        upsert=True,
    )
    if await database.db.settings.aria2c.find_one({"_id": TgClient.ID}) is None:
        await database.db.settings.aria2c.update_one(
            {"_id": TgClient.ID},
            {"$set": aria2_options},
            upsert=True,
        )
    if await database.db.settings.qbittorrent.find_one({"_id": TgClient.ID}) is None:
        await database.save_qbit_settings()
    if await database.db.settings.nzb.find_one({"_id": TgClient.ID}) is None:
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await database.db.settings.nzb.update_one(
            {"_id": TgClient.ID},
            {"$set": {"SABnzbd__ini": nzb_conf}},
            upsert=True,
        )


async def update_variables():
    """Updates various global configuration variables and lists based on the
    loaded Config values. This includes setting up authorized chats, sudo users,
    excluded extensions, drive lists, and attempting to determine the BASE_URL
    if running on Heroku.
    """
    if (
        Config.LEECH_SPLIT_SIZE > TgClient.MAX_SPLIT_SIZE
        or Config.LEECH_SPLIT_SIZE == 2097152000
        or not Config.LEECH_SPLIT_SIZE
    ):
        Config.LEECH_SPLIT_SIZE = TgClient.MAX_SPLIT_SIZE

    Config.HYBRID_LEECH = bool(Config.HYBRID_LEECH and TgClient.IS_PREMIUM_USER)
    Config.USER_TRANSMISSION = bool(
        Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER,
    )

    if Config.AUTHORIZED_CHATS:
        aid = Config.AUTHORIZED_CHATS.split()
        for id_ in aid:
            chat_id, *thread_ids = id_.split("|")
            chat_id = int(chat_id.strip())
            if thread_ids:
                thread_ids = [int(x.strip()) for x in thread_ids]
                auth_chats[chat_id] = thread_ids
            else:
                auth_chats[chat_id] = []

    if Config.SUDO_USERS:
        aid = Config.SUDO_USERS.split()
        for id_ in aid:
            sudo_users.append(int(id_.strip()))

    if Config.EXCLUDED_EXTENSIONS:
        fx = Config.EXCLUDED_EXTENSIONS.split()
        for x in fx:
            x = x.lstrip(".")
            excluded_extensions.append(x.strip().lower())

    if Config.INCLUDED_EXTENSIONS:
        fx = Config.INCLUDED_EXTENSIONS.split()
        for x in fx:
            x = x.lstrip(".")
            included_extensions.append(x.strip().lower())
    if Config.GDRIVE_ID:
        drives_names.append("Main")
        drives_ids.append(Config.GDRIVE_ID)
        index_urls.append(Config.INDEX_URL)

    if await aiopath.exists("list_drives.txt"):
        async with aiopen("list_drives.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.split()
                drives_ids.append(temp[1])
                drives_names.append(temp[0].replace("_", " "))
                if len(temp) > 2:
                    index_urls.append(temp[2])
                else:
                    index_urls.append("")

    if Config.HEROKU_APP_NAME and Config.HEROKU_API_KEY:
        headers = {
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {Config.HEROKU_API_KEY}",
        }

        urls = [
            f"https://api.heroku.com/teams/apps/{Config.HEROKU_APP_NAME}",
            f"https://api.heroku.com/apps/{Config.HEROKU_APP_NAME}",
        ]

        async with aiohttp.ClientSession(headers=headers) as session:
            for url in urls:
                try:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        app_data = await response.json()
                        if web_url := app_data.get("web_url"):
                            Config.set("BASE_URL", web_url.rstrip("/"))
                            return
                except Exception as e:
                    LOGGER.error(f"BASE_URL error: {e}")
                    continue


async def load_configurations():
    """Performs initial setup for configurations like .netrc,
    starts the Gunicorn web server, extracts JDownloader config if present,
    loads shorteners, and sets up service accounts if accounts.zip exists.
    """

    process = await create_subprocess_shell(
        "uv pip install -U truelink",
    )
    await process.wait()
    from truelink import TrueLinkResolver

    from bot.helper.mirror_leech_utils.download_utils.insta_resolver import (
        InstagramResolver,
    )

    _ = TrueLinkResolver()
    TrueLinkResolver.register_resolver("instagram.com", InstagramResolver)

    if not await aiopath.exists(".netrc"):
        async with aiopen(".netrc", "w"):
            pass
    await (
        await create_subprocess_shell(
            "chmod 600 .netrc && cp .netrc /root/.netrc && chmod +x aria.sh && ./aria.sh",
        )
    ).wait()

    PORT = int(environ.get("PORT") or environ.get("BASE_URL_PORT") or "80")
    await create_subprocess_shell(
        f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{PORT}",
    )

    if await aiopath.exists("cfg.zip"):
        if await aiopath.exists("/JDownloader/cfg"):
            await rmtree("/JDownloader/cfg", ignore_errors=True)
        await (
            await create_subprocess_exec("7z", "x", "cfg.zip", "-o/JDownloader")
        ).wait()

    if await aiopath.exists("shorteners.txt"):
        async with aiopen("shorteners.txt") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.strip().split()
                if len(temp) == 2:
                    shorteners_list.append({"domain": temp[0], "api_key": temp[1]})

    if await aiopath.exists("accounts.zip"):
        if await aiopath.exists("accounts"):
            await rmtree("accounts")
        await (
            await create_subprocess_exec(
                "7z",
                "x",
                "-o.",
                "-aoa",
                "accounts.zip",
                "accounts/*.json",
            )
        ).wait()
        await (await create_subprocess_exec("chmod", "-R", "777", "accounts")).wait()
        await remove("accounts.zip")

    if not await aiopath.exists("accounts"):
        Config.USE_SERVICE_ACCOUNTS = False
