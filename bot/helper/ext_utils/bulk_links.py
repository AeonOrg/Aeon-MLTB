from aiofiles import open as aiopen
from aiofiles.os import remove


def filter_links(links_list, bulk_start, bulk_end):
    start = bulk_start if bulk_start > 0 else None
    end = bulk_end if bulk_end > 0 else None
    return links_list[start:end]


def get_links_from_message(text: str) -> list:
    """
    Extracts links from a string, assuming one link per line.
    Empty lines are ignored.

    Args:
        text: The string containing links.

    Returns:
        A list of extracted links.
    """
    links_list = text.split("\n")
    return [item.strip() for item in links_list if len(item) != 0]


async def get_links_from_file(message) -> list:
    """
    Downloads a text file attached to a Pyrogram message and extracts links from it,
    assuming one link per line. Empty lines are ignored.

    Args:
        message: The Pyrogram message object with the attached text file.

    Returns:
        A list of extracted links.
    """
    links_list = []
    text_file_dir = await message.download()
    async with aiopen(text_file_dir, "r+") as f:
        lines = await f.readlines()
        links_list.extend(line.strip() for line in lines if len(line) != 0)
    await remove(text_file_dir)
    return links_list


async def extract_bulk_links(message, bulk_start: str, bulk_end: str) -> list:
    """
    Extracts bulk links from a Pyrogram message.
    Links can be in the replied-to message's text or an attached text file.
    The extracted links are then filtered based on start and end indices.

    Args:
        message: The Pyrogram message object.
        bulk_start: The starting index for filtering (string, converted to int).
        bulk_end: The ending index for filtering (string, converted to int).

    Returns:
        A list of filtered links.
    """
    bulk_start = int(bulk_start)
    bulk_end = int(bulk_end)
    links_list = []
    if reply_to := message.reply_to_message:
        if (file_ := reply_to.document) and (file_.mime_type == "text/plain"):
            links_list = await get_links_from_file(reply_to)
        elif text := reply_to.text:
            links_list = get_links_from_message(text)
    return (
        filter_links(links_list, bulk_start, bulk_end) if links_list else links_list
    )
