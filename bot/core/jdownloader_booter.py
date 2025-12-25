from json import dump
from random import randint
from re import match

from aiofiles.os import listdir, makedirs, path, rename
from aioshutil import rmtree

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec, new_task
from myjd import MyJdApi

from .config_manager import Config
from .telegram_manager import TgClient


class JDownloader(MyJdApi):
    def __init__(self):
        super().__init__()
        self._username = ""
        self._password = ""
        self._device_name = ""
        self.is_connected = False
        self.error = "JDownloader Credentials not provided!"

    @new_task
    async def boot(self):
        """Initializes and starts the JDownloader process,
        configuring it with credentials and necessary settings.
        """
        await cmd_exec(["pkill", "-9", "-f", "java"])
        if not Config.JD_EMAIL or not Config.JD_PASS:
            self.is_connected = False
            self.error = "JDownloader Credentials not provided!"
            return
        self.error = "Connecting... Try again after a few seconds."
        self._device_name = f"{randint(0, 1000)}@{TgClient.NAME}"
        if await path.exists("/JDownloader/logs"):
            LOGGER.info(
                "Starting JDownloader... This might take up to 10 seconds and might restart once if an update is available.",
            )
        else:
            LOGGER.info(
                "Starting JDownloader... This might take up to 8 seconds and might restart once after build.",
            )
        jdata = {
            "autoconnectenabledv2": True,
            "password": Config.JD_PASS,
            "devicename": f"{self._device_name}",
            "email": Config.JD_EMAIL,
        }
        remote_data = {
            "localapiserverheaderaccesscontrollalloworigin": "",
            "deprecatedapiport": 3128,
            "localapiserverheaderxcontenttypeoptions": "nosniff",
            "localapiserverheaderxframeoptions": "DENY",
            "externinterfaceenabled": True,
            "deprecatedapilocalhostonly": True,
            "localapiserverheaderreferrerpolicy": "no-referrer",
            "deprecatedapienabled": True,
            "localapiserverheadercontentsecuritypolicy": "default-src 'self'",
            "jdanywhereapienabled": True,
            "externinterfacelocalhostonly": False,
            "localapiserverheaderxxssprotection": "1; mode=block",
        }
        await makedirs("/JDownloader/cfg", exist_ok=True)
        with open(  # noqa: ASYNC230
            "/JDownloader/cfg/org.jdownloader.api.myjdownloader.MyJDownloaderSettings.json",
            "w",
        ) as sf:
            sf.truncate(0)
            dump(jdata, sf)
        with open(  # noqa: ASYNC230
            "/JDownloader/cfg/org.jdownloader.api.RemoteAPIConfig.json",
            "w",
        ) as rf:
            rf.truncate(0)
            dump(remote_data, rf)
        if not await path.exists("/JDownloader/JDownloader.jar"):
            pattern = r"JDownloader\.jar\.backup.\d$"
            for filename in await listdir("/JDownloader"):
                if match(pattern, filename):
                    await rename(
                        f"/JDownloader/{filename}",
                        "/JDownloader/JDownloader.jar",
                    )
                    break
            try:
                await rmtree("/JDownloader/update")
                await rmtree("/JDownloader/tmp")
            except Exception:
                pass

        cmd = "cpulimit -l 30 -- java -Xms256m -Xmx500m -Dsun.jnu.encoding=UTF-8 -Dfile.encoding=UTF-8 -Djava.awt.headless=true -jar /JDownloader/JDownloader.jar"

        self.is_connected = True
        _, __, code = await cmd_exec(cmd, shell=True)
        self.is_connected = False
        if code != -9:
            await self.boot()


jdownloader = JDownloader()
