import os
from datetime import datetime
from importlib import import_module
from logging import (
    ERROR,
    INFO,
    FileHandler,
    Formatter,
    LogRecord,
    StreamHandler,
    basicConfig,
    getLogger,
)
from logging import (
    error as log_error,
)
from logging import (
    info as log_info,
)
from os import path, remove
from subprocess import run as srun
from sys import exit

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pytz import timezone

getLogger("pymongo").setLevel(ERROR)

if path.exists("log.txt"):
    with open("log.txt", "r+") as f:
        f.truncate(0)

if path.exists("rlog.txt"):
    remove("rlog.txt")


class CustomFormatter(Formatter):
    def formatTime(  # noqa: N802
        self,
        record: LogRecord,
        datefmt: str | None,
    ) -> str:
        dt: datetime = datetime.fromtimestamp(
            record.created,
            tz=timezone("Asia/Dhaka"),
        )
        return dt.strftime(datefmt)

    def format(self, record: LogRecord) -> str:
        return super().format(record).replace(record.levelname, record.levelname[:1])


formatter = CustomFormatter(
    "[%(asctime)s] %(levelname)s - %(message)s [%(module)s:%(lineno)d]",
    datefmt="%d-%b %I:%M:%S %p",
)

file_handler = FileHandler("log.txt")
file_handler.setFormatter(formatter)

stream_handler = StreamHandler()
stream_handler.setFormatter(formatter)

basicConfig(handlers=[file_handler, stream_handler], level=INFO)

# Attempt to load from config.py
try:
    settings = import_module("config")
    config_file = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in vars(settings).items()
    }
except Exception:
    log_info(
        "The 'config.py' file is missing! Falling back to environment variables.",
    )
    config_file = {}

# Fallback to environment variables if BOT_TOKEN is not set
BOT_TOKEN = config_file.get("BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    log_error("BOT_TOKEN variable is missing! Exiting now.")
    exit(1)

BOT_ID = BOT_TOKEN.split(":", 1)[0]

# Fallback to environment variables for DATABASE_URL
DATABASE_URL = config_file.get("DATABASE_URL", "") or os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    try:
        conn = MongoClient(DATABASE_URL, server_api=ServerApi("1"))
        db = conn.luna
        config_dict = db.settings.config.find_one({"_id": BOT_ID})
        if config_dict is not None:
            config_file["UPSTREAM_REPO"] = config_dict.get(
                "UPSTREAM_REPO",
                config_file.get("UPSTREAM_REPO"),
            )
            config_file["UPSTREAM_BRANCH"] = config_dict.get(
                "UPSTREAM_BRANCH",
                config_file.get("UPSTREAM_BRANCH"),
            )
        conn.close()
    except Exception as e:
        log_error(f"Database ERROR: {e}")

UPSTREAM_REPO = (
    config_file.get("UPSTREAM_REPO", "")
    or os.getenv("UPSTREAM_REPO", "")
    or "https://github.com/AeonOrg/Aeon-MLTB"
)

UPSTREAM_BRANCH = (
    config_file.get("UPSTREAM_BRANCH", "")
    or os.getenv("UPSTREAM_BRANCH", "")
    or "main"
)

if UPSTREAM_REPO:
    if path.exists(".git"):
        srun(["rm", "-rf", ".git"], check=False)

    update = srun(
        [
            f"git init -q \
                     && git config --global user.email e.anastayyar@gmail.com \
                     && git config --global user.name mltb \
                     && git add . \
                     && git commit -sm update -q \
                     && git remote add origin {UPSTREAM_REPO} \
                     && git fetch origin -q \
                     && git reset --hard origin/{UPSTREAM_BRANCH} -q",
        ],
        shell=True,
        check=False,
    )

    if update.returncode == 0:
        log_info("Successfully updated with latest commit from UPSTREAM_REPO")
    else:
        log_error(
            "Something went wrong while updating, check UPSTREAM_REPO if valid or not!",
        )
