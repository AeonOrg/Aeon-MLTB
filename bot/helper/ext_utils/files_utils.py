from asyncio import create_subprocess_exec, wait_for
from asyncio.subprocess import PIPE
from os import path as ospath
from os import readlink, walk
from re import IGNORECASE, escape
from re import search as re_search
from re import split as re_split

from aiofiles.os import (
    listdir,
    remove,
    rmdir,
    symlink,
)
from aiofiles.os import (
    makedirs as aiomakedirs,
)
from aiofiles.os import (
    path as aiopath,
)
from aiofiles.os import (
    readlink as aioreadlink,
)
from aioshutil import rmtree as aiormtree
from magic import Magic

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.torrent_manager import TorrentManager

from .bot_utils import cmd_exec, sync_to_async
from .exceptions import NotSupportedExtractionArchive

ARCH_EXT = [
    ".tar.bz2",
    ".tar.gz",
    ".bz2",
    ".gz",
    ".tar.xz",
    ".tar",
    ".tbz2",
    ".tgz",
    ".lzma2",
    ".zip",
    ".7z",
    ".z",
    ".rar",
    ".iso",
    ".wim",
    ".cab",
    ".apm",
    ".arj",
    ".chm",
    ".cpio",
    ".cramfs",
    ".deb",
    ".dmg",
    ".fat",
    ".hfs",
    ".lzh",
    ".lzma",
    ".mbr",
    ".msi",
    ".mslz",
    ".nsis",
    ".ntfs",
    ".rpm",
    ".squashfs",
    ".udf",
    ".vhd",
    ".xar",
    ".zst",
    ".zstd",
    ".cbz",
    ".apfs",
    ".ar",
    ".qcow",
    ".macho",
    ".exe",
    ".dll",
    ".sys",
    ".pmd",
    ".swf",
    ".swfc",
    ".simg",
    ".vdi",
    ".vhdx",
    ".vmdk",
    ".gzip",
    ".lzma86",
    ".sha256",
    ".sha512",
    ".sha224",
    ".sha384",
    ".sha1",
    ".md5",
    ".crc32",
    ".crc64",
]

FIRST_SPLIT_REGEX = (
    r"\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$|^(?!.*\.part\d+\.rar$).*\.rar$"
)

SPLIT_REGEX = r"\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$|\.part\d+\.rar$"


def is_first_archive_split(file: str) -> bool:
    """Checks if the filename matches the pattern for the first part of a split archive."""
    return bool(re_search(FIRST_SPLIT_REGEX, file.lower(), IGNORECASE))


def is_archive(file: str) -> bool:
    """Checks if the file is an archive based on its extension."""
    return file.strip().lower().endswith(tuple(ARCH_EXT))


def is_archive_split(file: str) -> bool:
    """Checks if the filename matches the pattern for a part of a split archive."""
    return bool(re_search(SPLIT_REGEX, file.lower(), IGNORECASE))


async def clean_target(path: str):
    """Removes the file or directory at the given path."""
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning target: {path}")
        try:
            if await aiopath.isdir(path):
                await aiormtree(path, ignore_errors=True)
            else:
                await remove(path)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_download(path: str):
    """Removes the downloaded file or directory at the given path."""
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning download: {path}")
        try:
            await aiormtree(path, ignore_errors=True)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_all():
    """Cleans up all torrents and the main download directory."""
    await TorrentManager.remove_all()
    LOGGER.info("Cleaning Download Directory...")
    await (await create_subprocess_exec("rm", "-rf", DOWNLOAD_DIR)).wait()
    await aiomakedirs(DOWNLOAD_DIR, exist_ok=True)


async def clean_unwanted(opath: str):
    """Removes unwanted files (e.g., .parts) and empty .unwanted directories."""
    LOGGER.info(f"Cleaning unwanted files/folders from: {opath}")
    for dirpath, _, files in await sync_to_async(walk, opath, topdown=False):
        for filee in files:
            f_path = ospath.join(dirpath, filee)
            if filee.strip().endswith(".parts") and filee.startswith("."):
                await remove(f_path)
        if dirpath.strip().endswith(".unwanted"):
            await aiormtree(dirpath, ignore_errors=True)
    for dirpath, _, __ in await sync_to_async(walk, opath, topdown=False):
        if not await listdir(dirpath):
            await rmdir(dirpath)


async def get_path_size(opath: str) -> int:
    """Calculates the total size of a file or directory (recursively for directories).
    Follows symbolic links for files.
    """
    total_size = 0
    if await aiopath.isfile(opath):
        if await aiopath.islink(opath):
            opath = await aioreadlink(opath)
        return await aiopath.getsize(opath)
    for root, _, files in await sync_to_async(walk, opath):
        for f in files:
            abs_path = ospath.join(root, f)
            if await aiopath.islink(abs_path):
                abs_path = await aioreadlink(abs_path)
            total_size += await aiopath.getsize(abs_path)
    return total_size


async def count_files_and_folders(opath: str) -> tuple[int, int]:
    """Counts the total number of files and folders within a given path."""
    total_files = 0
    total_folders = 0
    for _, dirs, files in await sync_to_async(walk, opath):
        total_files += len(files)
        total_folders += len(dirs)
    return total_folders, total_files


def get_base_name(orig_path: str) -> str:
    """Extracts the base name of a file, removing known archive extensions.
    Raises NotSupportedExtractionArchive if the extension is not found in ARCH_EXT.
    """
    extension = next(
        (ext for ext in ARCH_EXT if orig_path.strip().lower().endswith(ext)),
        "",
    )
    if extension != "":
        return re_split(f"{extension}$", orig_path, maxsplit=1, flags=IGNORECASE)[0]
    raise NotSupportedExtractionArchive("File format not supported for extraction")


async def create_recursive_symlink(source: str, destination: str):
    """Creates symbolic links recursively from source to destination.
    If source is a directory, it replicates the directory structure with symlinks.
    If source is a file, it creates a symlink for that file.
    """
    if ospath.isdir(source):
        await aiomakedirs(destination, exist_ok=True)
        for item in await listdir(source):
            item_source = ospath.join(source, item)
            item_dest = ospath.join(destination, item)
            await create_recursive_symlink(item_source, item_dest)
    elif ospath.isfile(source):
        try:
            await symlink(source, destination)
        except FileExistsError:
            LOGGER.error(f"Shortcut already exists: {destination}")
        except Exception as e:
            LOGGER.error(f"Error creating shortcut for {source}: {e}")


def get_mime_type(file_path: str) -> str:
    """Determines the MIME type of a file. Follows symbolic links."""
    if ospath.islink(file_path):
        file_path = readlink(file_path)
    mime = Magic(mime=True)
    mime_type = mime.from_file(file_path)
    return mime_type or "text/plain"


async def remove_excluded_files(fpath, ee):
    for root, _, files in await sync_to_async(walk, fpath):
        if root.strip().endswith("/yt-dlp-thumb"):
            continue
        for f in files:
            if f.strip().lower().endswith(tuple(ee)):
                await remove(ospath.join(root, f))


async def remove_non_included_files(fpath, ie):
    for root, _, files in await sync_to_async(walk, fpath):
        if root.strip().endswith("/yt-dlp-thumb"):
            continue
        for f in files:
            if f.strip().lower().endswith(tuple(ie)):
                continue
            await remove(ospath.join(root, f))


async def join_files(opath):
    files = await listdir(opath)
    results = []
    exists = False
    for file_ in files:
        if re_search(r"\.0+2$", file_) and await sync_to_async(
            get_mime_type,
            f"{opath}/{file_}",
        ) not in ["application/x-7z-compressed", "application/zip"]:
            exists = True
            final_name = file_.rsplit(".", 1)[0]
            fpath = f"{opath}/{final_name}"
            cmd = f'cat "{fpath}."* > "{fpath}"'
            _, stderr, code = await cmd_exec(cmd, True)
            if code != 0:
                LOGGER.error(f"Failed to join {final_name}, stderr: {stderr}")
                if await aiopath.isfile(fpath):
                    await remove(fpath)
            else:
                results.append(final_name)

    if not exists:
        LOGGER.warning("No files to join!")
    elif results:
        LOGGER.info("Join Completed!")
        for res in results:
            for file_ in files:
                if re_search(rf"{escape(res)}\.0[0-9]+$", file_):
                    await remove(f"{opath}/{file_}")


async def split_file(f_path, split_size, listener):
    out_path = f"{f_path}."
    if listener.is_cancelled:
        return False
    listener.subproc = await create_subprocess_exec(
        "split",
        "--numeric-suffixes=1",
        "--suffix-length=3",
        f"--bytes={split_size}",
        f_path,
        out_path,
        stderr=PIPE,
    )
    _, stderr = await listener.subproc.communicate()
    code = listener.subproc.returncode
    if listener.is_cancelled:
        return False
    if code == -9:
        listener.is_cancelled = True
        return False
    if code != 0:
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(f"{stderr}. Split Document: {f_path}")
    return True


class SevenZ:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._percentage = "0%"

    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def progress(self):
        return self._percentage

    async def _sevenz_progress(self):
        pattern = r"(\d+)\s+bytes|Total Physical Size\s*=\s*(\d+)|Physical Size\s*=\s*(\d+)"
        while not (
            self._listener.subproc.returncode is not None
            or self._listener.is_cancelled
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                line = await wait_for(self._listener.subproc.stdout.readline(), 2)
            except Exception:
                break
            line = line.decode().strip()
            if "%" in line:
                perc = line.split("%", 1)[0]
                if perc.isdigit():
                    self._percentage = f"{perc}%"
                    self._processed_bytes = (
                        int(perc) / 100
                    ) * self._listener.subsize
                else:
                    self._percentage = "0%"
                continue
            if match := re_search(pattern, line):
                self._listener.subsize = int(match[1] or match[2] or match[3])
        s = b""
        while not (
            self._listener.is_cancelled
            or self._listener.subproc.returncode is not None
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                char = await wait_for(self._listener.subproc.stdout.read(1), 60)
            except Exception:
                break
            if not char:
                break
            s += char
            if char == b"%":
                try:
                    self._percentage = s.decode().rsplit(" ", 1)[-1].strip()
                    self._processed_bytes = (
                        int(self._percentage.strip("%")) / 100
                    ) * self._listener.subsize
                except Exception:
                    self._processed_bytes = 0
                    self._percentage = "0%"
                s = b""

        self._processed_bytes = 0
        self._percentage = "0%"

    async def extract(self, f_path, t_path, pswd):
        cmd = [
            "7z",
            "x",
            f"-p{pswd}",
            f_path,
            f"-o{t_path}",
            "-aot",
            "-xr!@PaxHeader",
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if not pswd:
            del cmd[2]
        if self._listener.is_cancelled:
            return False
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode
        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code != 0:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(f"{stderr}. Unable to extract archive!. Path: {f_path}")
        return code

    async def zip(self, dl_path, up_path, pswd):
        size = await get_path_size(dl_path)
        split_size = self._listener.split_size
        cmd = [
            "7z",
            f"-v{split_size}b",
            "a",
            "-mx=0",
            f"-p{pswd}",
            up_path,
            dl_path,
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if self._listener.is_leech and int(size) > self._listener.split_size:
            if not pswd:
                del cmd[4]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}.0*")
        else:
            del cmd[1]
            if not pswd:
                del cmd[3]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}")
        if self._listener.is_cancelled:
            return False
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode
        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code == 0:
            await clean_target(dl_path)
            return up_path
        if await aiopath.exists(up_path):
            await remove(up_path)
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(f"{stderr}. Unable to zip this path: {dl_path}")
        return dl_path
