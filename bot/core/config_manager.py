import ast
import os
from importlib import import_module
from typing import Any, ClassVar


class Config:
    AS_DOCUMENT: bool = False
    AUTHORIZED_CHATS: str = ""
    BASE_URL: str = ""
    BASE_URL_PORT: int = 80
    BOT_TOKEN: str = ""
    CMD_SUFFIX: str = ""
    DATABASE_URL: str = ""
    DEFAULT_UPLOAD: str = "rc"
    EXCLUDED_EXTENSIONS: str = ""
    FFMPEG_CMDS: ClassVar[dict[str, list[str]]] = {}
    FILELION_API: str = ""
    GDRIVE_ID: str = ""
    INCOMPLETE_TASK_NOTIFIER: bool = False
    INDEX_URL: str = ""
    JD_EMAIL: str = ""
    JD_PASS: str = ""
    IS_TEAM_DRIVE: bool = False
    LEECH_DUMP_CHAT: str = ""
    LEECH_FILENAME_PREFIX: str = ""
    LEECH_SPLIT_SIZE: int = 2097152000
    MEDIA_GROUP: bool = False
    HYBRID_LEECH: bool = False
    NAME_SUBSTITUTE: str = ""
    OWNER_ID: int = 0
    QUEUE_ALL: int = 0
    QUEUE_DOWNLOAD: int = 0
    QUEUE_UPLOAD: int = 0
    RCLONE_FLAGS: str = ""
    RCLONE_PATH: str = ""
    RCLONE_SERVE_URL: str = ""
    RCLONE_SERVE_USER: str = ""
    RCLONE_SERVE_PASS: str = ""
    RCLONE_SERVE_PORT: int = 8080
    RSS_CHAT: str = ""
    RSS_DELAY: int = 600
    RSS_SIZE_LIMIT: int = 0
    STOP_DUPLICATE: bool = False
    STREAMWISH_API: str = ""
    SUDO_USERS: str = ""
    TELEGRAM_API: int = 0
    TELEGRAM_HASH: str = ""
    TG_PROXY: dict | None = None
    THUMBNAIL_LAYOUT: str = ""
    TORRENT_TIMEOUT: int = 0
    UPLOAD_PATHS: dict = {}
    UPSTREAM_REPO: str = ""
    USENET_SERVERS: list = []
    UPSTREAM_BRANCH: str = "main"
    USER_SESSION_STRING: str = ""
    USER_TRANSMISSION: bool = False
    USE_SERVICE_ACCOUNTS: bool = False
    WEB_PINCODE: bool = False
    YT_DLP_OPTIONS: dict = {}

    # INKYPINKY
    METADATA_KEY: str = ""
    WATERMARK_KEY: str = ""
    SET_COMMANDS: bool = True
    TOKEN_TIMEOUT: int = 0
    PAID_CHANNEL_ID: int = 0
    PAID_CHANNEL_LINK: str = ""
    DELETE_LINKS: bool = False
    FSUB_IDS: str = ""
    LOG_CHAT_ID: int = 0
    LEECH_FILENAME_CAPTION: str = ""
    HYDRA_IP: str = ""
    HYDRA_API_KEY: str = ""

    @classmethod
    def get(cls, key):
        return getattr(cls, key) if hasattr(cls, key) else None

    @classmethod
    def set(cls, key, value):
        if hasattr(cls, key):
            setattr(cls, key, value)
        else:
            raise KeyError(f"{key} is not a valid configuration key.")

    @classmethod
    def get_all(cls):
        return {
            key: getattr(cls, key)
            for key in sorted(cls.__dict__)
            if not key.startswith("__") and not callable(getattr(cls, key))
        }

    @classmethod
    def load(cls):
        try:
            settings = import_module("config")
        except ModuleNotFoundError:
            return
        else:
            for attr in dir(settings):
                if hasattr(cls, attr):
                    value = getattr(settings, attr)
                    if not value:
                        continue
                    if isinstance(value, str):
                        value = value.strip()
                    if attr == "DEFAULT_UPLOAD" and value != "gd":
                        value = "rc"
                    elif (
                        attr
                        in [
                            "BASE_URL",
                            "RCLONE_SERVE_URL",
                            "INDEX_URL",
                        ]
                        and value
                    ):
                        value = value.strip("/")
                    elif attr == "USENET_SERVERS":
                        try:
                            if not value[0].get("host"):
                                continue
                        except Exception:
                            continue
                    setattr(cls, attr, value)

    @classmethod
    def load_dict(cls, config_dict):
        for key, value in config_dict.items():
            if hasattr(cls, key):
                if key == "DEFAULT_UPLOAD" and value != "gd":
                    value = "rc"
                elif (
                    key
                    in [
                        "BASE_URL",
                        "RCLONE_SERVE_URL",
                        "INDEX_URL",
                    ]
                    and value
                ):
                    value = value.strip("/")
                elif key == "USENET_SERVERS":
                    try:
                        if not value[0].get("host"):
                            value = []
                    except Exception:
                        value = []
                setattr(cls, key, value)


class SystemEnv:
    @classmethod
    def load(cls):
        config_vars = Config.get_all()
        for key in config_vars:
            env_value = os.getenv(key)
            if env_value is not None:
                converted_value = cls._convert_type(key, env_value)
                Config.set(key, converted_value)

    @classmethod
    def _convert_type(cls, key: str, value: str) -> Any:
        original_value = getattr(Config, key, None)

        if original_value is None:
            return value

        if isinstance(original_value, bool):
            return value.lower() in ("true", "1", "yes")

        if isinstance(original_value, int):
            try:
                return int(value)
            except ValueError:
                return original_value

        if isinstance(original_value, float):
            try:
                return float(value)
            except ValueError:
                return original_value

        if isinstance(original_value, list):
            return value.split(",")

        if isinstance(original_value, dict):
            try:
                return ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return original_value

        return value
