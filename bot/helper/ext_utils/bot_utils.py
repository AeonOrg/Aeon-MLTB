import contextlib
from asyncio import (
    create_subprocess_exec,
    create_subprocess_shell,
    run_coroutine_threadsafe,
    sleep,
)
from asyncio.subprocess import PIPE
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps

from httpx import AsyncClient

from bot import bot_loop, user_data
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker

from .help_messages import (
    CLONE_HELP_DICT,
    MIRROR_HELP_DICT,
    YT_HELP_DICT,
)
from .telegraph_helper import telegraph

COMMAND_USAGE = {}

THREAD_POOL = ThreadPoolExecutor(max_workers=500)


class SetInterval:
    """
    A class to mimic JavaScript's setInterval functionality, running a
    specified action at regular intervals.
    """

    def __init__(self, interval, action, *args, **kwargs):
        """
        Initializes the SetInterval timer.

        Args:
            interval: The time interval in seconds between executions.
            action: The awaitable function to execute.
            *args: Arguments to pass to the action.
            **kwargs: Keyword arguments to pass to the action.
        """
        self.interval = interval
        self.action = action
        self.task = bot_loop.create_task(self._set_interval(*args, **kwargs))

    async def _set_interval(self, *args, **kwargs):
        """The internal coroutine that runs the action periodically."""
        while True:
            await sleep(self.interval)
            await self.action(*args, **kwargs)

    def cancel(self):
        """Cancels the scheduled execution of the action."""
        self.task.cancel()


def _build_command_usage(help_dict, command_key):
    """
    Builds and stores command usage help messages and buttons
    for a given command key using its help dictionary.
    """
    buttons = ButtonMaker()
    for name in list(help_dict.keys())[1:]:
        buttons.data_button(name, f"help {command_key} {name}")
    buttons.data_button("Close", "help close")
    COMMAND_USAGE[command_key] = [help_dict["main"], buttons.build_menu(3)]
    buttons.reset()


def create_help_buttons():
    """Initializes help button structures for various primary commands."""
    _build_command_usage(MIRROR_HELP_DICT, "mirror")
    _build_command_usage(YT_HELP_DICT, "yt")
    _build_command_usage(CLONE_HELP_DICT, "clone")


def bt_selection_buttons(id_):
    """
    Generates buttons for BitTorrent file selection, including options for
    web-based selection with or without a PIN code.

    Args:
        id_: The identifier for the torrent (GID or hash).

    Returns:
        A ButtonMaker menu object.
    """
    gid = id_[:12] if len(id_) > 25 else id_
    pin = "".join([n for n in id_ if n.isdigit()][:4])
    buttons = ButtonMaker()
    if Config.WEB_PINCODE:
        buttons.url_button("Select Files", f"{Config.BASE_URL}/app/files?gid={id_}")
        buttons.data_button("Pincode", f"sel pin {gid} {pin}")
    else:
        buttons.url_button(
            "Select Files",
            f"{Config.BASE_URL}/app/files?gid={id_}&pin={pin}",
        )
    buttons.data_button("Done Selecting", f"sel done {gid} {id_}")
    buttons.data_button("Cancel", f"sel cancel {gid}")
    return buttons.build_menu(2)


async def get_telegraph_list(telegraph_content):
    """
    Creates Telegraph pages from the provided content list.
    If multiple content parts are provided, it attempts to edit them into a single series.

    Args:
        telegraph_content: A list of strings, where each string is the HTML content for a page.

    Returns:
        A ButtonMaker menu object with a button linking to the first Telegraph page.
    """
    path = [
        (
            await telegraph.create_page(
                title="Aeon-MLTB Drive Search",
                content=content,
            )
        )["path"]
        for content in telegraph_content
    ]
    if len(path) > 1:
        await telegraph.edit_telegraph(path, telegraph_content)
    buttons = ButtonMaker()
    buttons.url_button("🔎 VIEW", f"https://telegra.ph/{path[0]}")
    return buttons.build_menu(1)


def arg_parser(items, arg_base):
    """
    Parses a list of items (command arguments) and updates the arg_base dictionary.
    Handles boolean flags and arguments with values.

    Args:
        items: A list of strings representing command arguments.
        arg_base: A dictionary to populate with parsed arguments.
                  It should be pre-filled with expected argument keys.
    """
    if not items:
        return

    arg_start = -1
    i = 0
    total = len(items)

    bool_arg_set = {
        "-b",
        "-e",
        "-z",
        "-s",
        "-j",
        "-d",
        "-sv",
        "-ss",
        "-f",
        "-fd",
        "-fu",
        "-sync",
        "-hl",
        "-doc",
        "-med",
        "-ut",
        "-bt",
    }

    while i < total:
        part = items[i]
        if part in arg_base:
            if arg_start == -1:
                arg_start = i
            if (i + 1 == total and part in bool_arg_set) or part in [
                "-s",
                "-j",
                "-f",
                "-fd",
                "-fu",
                "-sync",
                "-hl",
                "-doc",
                "-med",
                "-ut",
                "-bt",
            ]:
                arg_base[part] = True
            else:
                sub_list = []
                for j in range(i + 1, total):
                    if items[j] in arg_base:
                        if part == "-c" and items[j] == "-c":
                            sub_list.append(items[j])
                            continue
                        if part in bool_arg_set and not sub_list:
                            arg_base[part] = True
                            break
                        if not sub_list:
                            break
                        check = " ".join(sub_list).strip()
                        if part != "-ff":
                            break
                        if (
                            check.startswith("[") and check.endswith("]")
                        ) or not check.startswith("["):
                            break
                    sub_list.append(items[j])
                if sub_list:
                    value = " ".join(sub_list)
                    if part == "-ff":
                        if not value.strip().startswith("["):
                            arg_base[part].add(value)
                        else:
                            with contextlib.suppress(Exception):
                                arg_base[part].add(tuple(eval(value)))
                    else:
                        arg_base[part] = value
                    i += len(sub_list)
        i += 1
    if "link" in arg_base:
        link_items = items[:arg_start] if arg_start != -1 else items
        if link_items:
            arg_base["link"] = " ".join(link_items)


def get_size_bytes(size):
    """
    Converts a human-readable size string (e.g., '10K', '5M', '2G', '1T')
    to bytes.

    Args:
        size: The size string.

    Returns:
        The size in bytes as an integer, or 0 if the format is unrecognized.
    """
    size = size.lower()
    if "k" in size:
        size = int(float(size.split("k")[0]) * 1024)
    elif "m" in size:
        size = int(float(size.split("m")[0]) * 1048576)
    elif "g" in size:
        size = int(float(size.split("g")[0]) * 1073741824)
    elif "t" in size:
        size = int(float(size.split("t")[0]) * 1099511627776)
    else:
        size = 0
    return size


async def get_content_type(url):
    """
    Fetches the Content-Type header for a given URL.

    Args:
        url: The URL to check.

    Returns:
        The Content-Type string or None if an error occurs or header is not found.
    """
    try:
        async with AsyncClient(follow_redirects=True, verify=False) as client:
            response = await client.head(url)
            if "Content-Type" not in response.headers:
                response = await client.get(url)
            return response.headers.get("Content-Type")
    except Exception:
        return None


def update_user_ldata(id_, key, value):
    """
    Updates or adds a key-value pair to a user's data in the global user_data dictionary.

    Args:
        id_: The user ID.
        key: The key for the data.
        value: The value to set for the key.
    """
    user_data.setdefault(id_, {})
    user_data[id_][key] = value


async def cmd_exec(cmd, shell=False):
    """
    Executes a shell command asynchronously.

    Args:
        cmd: The command to execute (list of arguments or string if shell=True).
        shell: Whether to use the shell for execution (default: False).

    Returns:
        A tuple (stdout_str, stderr_str, return_code).
    """
    if shell:
        proc = await create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)
    else:
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await proc.communicate()
    try:
        stdout = stdout.decode().strip()
    except Exception:
        stdout = "Unable to decode the response!"
    try:
        stderr = stderr.decode().strip()
    except Exception:
        stderr = "Unable to decode the error!"
    return stdout, stderr, proc.returncode


def new_task(func):
    """Decorator to run the wrapped awaitable function as a new task in the bot's event loop."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        return bot_loop.create_task(func(*args, **kwargs))

    return wrapper


async def sync_to_async(func, *args, wait=True, **kwargs):
    """
    Runs a synchronous function asynchronously in a dedicated thread pool.

    Args:
        func: The synchronous function to run.
        *args: Arguments to pass to the function.
        wait: If True (default), awaits the result. Otherwise, returns the future.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the function if wait is True, otherwise the Future object.
    """
    pfunc = partial(func, *args, **kwargs)
    future = bot_loop.run_in_executor(THREAD_POOL, pfunc)
    return await future if wait else future


def async_to_sync(func, *args, wait=True, **kwargs):
    """
    Runs an asynchronous function synchronously from a thread by submitting it
    to the bot's event loop.

    Args:
        func: The asynchronous (awaitable) function to run.
        *args: Arguments to pass to the function.
        wait: If True (default), waits for and returns the result. Otherwise, returns the future.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the coroutine if wait is True, otherwise the Future object.
    """
    future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
    return future.result() if wait else future


def loop_thread(func):
    """
    Decorator to run an awaitable function in the bot's event loop
    from a synchronous context, typically another thread.
    """

    @wraps(func)
    def wrapper(*args, wait=False, **kwargs):
        future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
        return future.result() if wait else future

    return wrapper
