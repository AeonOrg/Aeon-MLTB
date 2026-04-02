import json
import os
from contextlib import suppress
from hashlib import md5

from aiofiles.os import path as aiopath
from langcodes import Language

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)


class DefaultDict(dict):
    """A dictionary that returns a default value for a missing key."""

    def __missing__(self, key):
        return "Unknown"


async def generate_caption(filename, directory, caption_template):
    """
    Generates a caption for a media file based on its MediaInfo
    and a provided template.

    Args:
        filename: The name of the media file.
        directory: The directory where the file is located.
        caption_template: A string template for the caption with placeholders.

    Returns:
        A formatted caption string or the original filename if MediaInfo fails.
    """
    file_path = os.path.join(directory, filename)

    try:
        result = await cmd_exec(["mediainfo", "--Output=JSON", file_path])
        if result[1]:
            LOGGER.info(f"MediaInfo command output: {result[1]}")

        mediainfo_data = json.loads(result[0])
    except Exception as error:
        LOGGER.error(f"Failed to retrieve media info: {error}. File may not exist!")
        return filename

    media_data = mediainfo_data.get("media", {})
    track_data = media_data.get("track", [])
    video_metadata = next(
        (track for track in track_data if track["@type"] == "Video"),
        {},
    )
    audio_metadata = [track for track in track_data if track["@type"] == "Audio"]
    subtitle_metadata = [track for track in track_data if track["@type"] == "Text"]

    video_duration = round(float(video_metadata.get("Duration", 0)))
    video_quality = get_video_quality(video_metadata.get("Height", None))

    audio_languages = ", ".join(
        parse_audio_language("", audio)
        for audio in audio_metadata
        if audio.get("Language")
    )
    subtitle_languages = ", ".join(
        parse_subtitle_language("", subtitle)
        for subtitle in subtitle_metadata
        if subtitle.get("Language")
    )

    audio_languages = audio_languages or "Unknown"
    subtitle_languages = subtitle_languages or "Unknown"
    video_quality = video_quality or "Unknown"
    file_md5_hash = calculate_md5(file_path)

    caption_data = DefaultDict(
        filename=filename,
        size=get_readable_file_size(await aiopath.getsize(file_path)),
        duration=get_readable_time(video_duration, True),
        quality=video_quality,
        audios=audio_languages,
        subtitles=subtitle_languages,
        md5_hash=file_md5_hash,
    )

    return caption_template.format_map(caption_data)


def get_video_quality(height):
    """
    Determines video quality string (e.g., 720p, 1080p) based on video height.

    Args:
        height: The height of the video in pixels.

    Returns:
        A string representing the video quality, or "Unknown".
    """
    if height:
        quality_map = {
            480: "480p",
            540: "540p",
            720: "720p",
            1080: "1080p",
            2160: "2160p",
            4320: "4320p",
            8640: "8640p",
        }
        for threshold, quality in sorted(quality_map.items()):
            if int(height) <= threshold:
                return quality
    return "Unknown"


def parse_audio_language(existing_languages, audio_stream):
    """
    Parses the language from an audio stream and appends its display name
    to the existing languages string if not already present.

    Args:
        existing_languages: A string of already parsed audio languages.
        audio_stream: A dictionary representing an audio stream from MediaInfo.

    Returns:
        An updated string of audio languages.
    """
    language_code = audio_stream.get("Language")
    if language_code:
        with suppress(Exception):
            language_name = Language.get(language_code).display_name()
            if language_name not in existing_languages:
                LOGGER.debug(f"Parsed audio language: {language_name}")
                existing_languages += f"{language_name}, "
    return existing_languages.strip(", ")


def parse_subtitle_language(existing_subtitles, subtitle_stream):
    """
    Parses the language from a subtitle stream and appends its display name
    to the existing subtitles string if not already present.

    Args:
        existing_subtitles: A string of already parsed subtitle languages.
        subtitle_stream: A dictionary representing a subtitle stream from MediaInfo.

    Returns:
        An updated string of subtitle languages.
    """
    subtitle_code = subtitle_stream.get("Language")
    if subtitle_code:
        with suppress(Exception):
            subtitle_name = Language.get(subtitle_code).display_name()
            if subtitle_name not in existing_subtitles:
                LOGGER.debug(f"Parsed subtitle language: {subtitle_name}")
                existing_subtitles += f"{subtitle_name}, "
    return existing_subtitles.strip(", ")


def calculate_md5(file_path):
    """
    Calculates the MD5 hash of the given file.

    Args:
        file_path: The path to the file.

    Returns:
        A hexadecimal string representing the MD5 hash.
    """
    md5_hash = md5()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()
