from asyncio import gather
from re import search as research
from time import time

from aiofiles.os import path as aiopath
from psutil import (
    boot_time,
    cpu_count,
    cpu_percent,
    disk_usage,
    net_io_counters,
    swap_memory,
    virtual_memory,
)

from bot import bot_start_time
from bot.helper.ext_utils.bot_utils import cmd_exec, new_task
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)

commands = {
    "aria2": (["xria", "--version"], r"aria2 version ([\d.]+)"),
    "qBittorrent": (["xnox", "--version"], r"qBittorrent v([\d.]+)"),
    "SABnzbd+": (["xnzb", "--version"], r"xnzb-([\d.]+)"),
    "python": (["python3", "--version"], r"Python ([\d.]+)"),
    "rclone": (["xone", "--version"], r"rclone v([\d.]+)"),
    "yt-dlp": (["yt-dlp", "--version"], r"([\d.]+)"),
    "ffmpeg": (["xtra", "-version"], r"ffmpeg version (n[\d.]+)"),
    "7z": (["7z", "i"], r"7-Zip ([\d.]+)"),
}


@new_task
async def bot_stats(_, message):
    total, used, free, disk = disk_usage("/")
    swap = swap_memory()
    memory = virtual_memory()
    stats = f"""
<b>Commit Date:</b> {commands["commit"]}

<b>Bot Uptime:</b> {get_readable_time(time() - bot_start_time)}
<b>OS Uptime:</b> {get_readable_time(time() - boot_time())}

<b>Total Disk Space:</b> {get_readable_file_size(total)}
<b>Used:</b> {get_readable_file_size(used)} | <b>Free:</b> {get_readable_file_size(free)}

<b>Upload:</b> {get_readable_file_size(net_io_counters().bytes_sent)}
<b>Download:</b> {get_readable_file_size(net_io_counters().bytes_recv)}

<b>CPU:</b> {cpu_percent(interval=0.5)}%
<b>RAM:</b> {memory.percent}%
<b>DISK:</b> {disk}%

<b>Physical Cores:</b> {cpu_count(logical=False)}
<b>Total Cores:</b> {cpu_count()}
<b>SWAP:</b> {get_readable_file_size(swap.total)} | <b>Used:</b> {swap.percent}%

<b>Memory Total:</b> {get_readable_file_size(memory.total)}
<b>Memory Free:</b> {get_readable_file_size(memory.available)}
<b>Memory Used:</b> {get_readable_file_size(memory.used)}

<b>python:</b> {commands["python"]}
<b>aria2:</b> {commands["aria2"]}
<b>qBittorrent:</b> {commands["qBittorrent"]}
<b>SABnzbd+:</b> {commands["SABnzbd+"]}
<b>rclone:</b> {commands["rclone"]}
<b>yt-dlp:</b> {commands["yt-dlp"]}
<b>ffmpeg:</b> {commands["ffmpeg"]}
<b>7z:</b> {commands["7z"]}
"""
    reply_message = await send_message(message, stats)
    await delete_message(message)
    await auto_delete_message(reply_message)


async def get_version_async(command, regex):
    try:
        out, err, code = await cmd_exec(command)
        if code != 0:
            return f"Error: {err}"
        match = research(regex, out)
        return match.group(1) if match else "Version not found"
    except Exception as e:
        return f"Exception: {e!s}"


@new_task
async def get_packages_version():
    tasks = [
        get_version_async(command, regex) for command, regex in commands.values()
    ]
    versions = await gather(*tasks)
    commands.update(dict(zip(commands.keys(), versions, strict=False)))
    if await aiopath.exists(".git"):
        last_commit = await cmd_exec(
            "git log -1 --date=short --pretty=format:'%cd <b>From</b> %cr'",
            True,
        )
        last_commit = last_commit[0]
    else:
        last_commit = "No UPSTREAM_REPO"
    commands["commit"] = last_commit
