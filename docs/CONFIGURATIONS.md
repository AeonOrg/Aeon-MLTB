## 1. Required Fields

| Variable        | Type   | Description                                                                                  |
|----------------|--------|----------------------------------------------------------------------------------------------|
| `BOT_TOKEN`     | `str`  | Telegram Bot Token obtained from [@BotFather](https://t.me/BotFather).                        |
| `OWNER_ID`      | `int`  | Telegram User ID (not username) of the bot's owner.                                           |
| `TELEGRAM_API`  | `int`  | API ID used to authenticate your Telegram account. Obtainable from [my.telegram.org](https://my.telegram.org). |
| `TELEGRAM_HASH` | `str`  | API hash used to authenticate your Telegram account. Obtainable from [my.telegram.org](https://my.telegram.org). |

## 2. Optional Fields

| Variable                  | Type           | Description |
|---------------------------|----------------|-------------|
| `TG_PROXY`                | `dict`         | Proxy settings as dict. Example: `{"scheme": "socks5", "hostname": "11.22.33.44", "port": 1234, "username": "user", "password": "pass"}`. Username/password optional. |
| `USER_SESSION_STRING`     | `str`          | Use to access Telegram premium features. Generate using `python3 generate_string_session.py`. **Note:** Use in supergroup only. |
| `DATABASE_URL`            | `str`          | MongoDB connection string. See [Create Database](https://github.com/anasty17/test?tab=readme-ov-file#create-database). Stores bot/user settings, RSS feeds, and task history. |
| `CMD_SUFFIX`              | `str` \| `int` | Suffix to add at the end of all commands. |
| `AUTHORIZED_CHATS`        | `str`          | User/Chat/Topic IDs to authorize. Format: `chat_id`, `chat_id|thread_id`, etc. Separate by spaces. |
| `SUDO_USERS`              | `str`          | User IDs with sudo permission. Separate by spaces. |
| `UPLOAD_PATHS`            | `dict`         | Dict with upload paths. Example: `{"path 1": "remote:", "path 2": "gdrive id", ...}` |
| `DEFAULT_UPLOAD`          | `str`          | `rc` for `RCLONE_PATH`, `gd` for `GDRIVE_ID`. Default: `rc`. [Read More](https://github.com/anasty17/mirror-leech-telegram-bot/tree/master#upload). |
| `INCLUDED_EXTENSIONS`     | `str`          | File extensions to be uploaded/cloned. `EXCLUDED_EXTENSIONS` will be ignore if you filled this ! Separate them by spaces. |
| `EXCLUDED_EXTENSIONS`     | `str`          | File extensions to skip during processing. Separate by spaces. |
| `INCOMPLETE_TASK_NOTIFIER`| `bool`         | Notify after restart for incomplete tasks. Requires `DATABASE_URL` and the bot to be in a supergroup. Default: `False`. |
| `FILELION_API`            | `str`          | API key from [FileLion](https://vidhide.com/?op=my_account). |
| `STREAMWISH_API`          | `str`          | API key from [StreamWish](https://streamwish.com/?op=my_account). |
| `YT_DLP_OPTIONS`          | `dict`         | Dict of `yt-dlp` options. [Docs](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184). [Convert script](https://t.me/mltb_official_channel/177). |
| `USE_SERVICE_ACCOUNTS`    | `bool`         | Use Google API service accounts. See [guide](https://github.com/anasty17/mirror-leech-telegram-bot#generate-service-accounts-what-is-service-account). |
| `FFMPEG_CMDS`             | `dict`         | Dict with lists of ffmpeg commands. Start with arguments only. Use `-ff key` to apply. Add `-del` to auto-delete source. See example and notes. |
| `NAME_SUBSTITUTE`         | `str`          | Replace/remove words/characters using `source/target` format. Use `\` for escaping special characters. |

## 3. GDrive Tools

| Variable        | Type   | Description |
|----------------|--------|-------------|
| `GDRIVE_ID`     | `str`  | Google Drive Folder/TeamDrive ID or `root`. |
| `IS_TEAM_DRIVE` | `bool` | Set `True` if `GDRIVE_ID` refers to a TeamDrive. Default: `False`. |
| `INDEX_URL`     | `str`  | Index URL for the Google Drive. [Reference](https://gitlab.com/ParveenBhadooOfficial/Google-Drive-Index). |
| `STOP_DUPLICATE`| `bool` | If `True`, the bot will check for duplicate file/folder names in Google Drive before uploading. Default: `False`. |

## 4. Rclone

| Variable            | Type   | Description |
|---------------------|--------|-------------|
| `RCLONE_PATH`        | `str`  | Default Rclone upload path (e.g., `myremote:path`). |
| `RCLONE_FLAGS`       | `str`  | Additional Rclone flags. Use `--key:value|--key` format. [Rclone Flags Docs](https://rclone.org/flags/). |
| `RCLONE_SERVE_URL`   | `str`  | URL for Rclone serve. Example: `http://myip` or `http://myip:port`. |
| `RCLONE_SERVE_PORT`  | `int`  | Port. Default: `8080`. |
| `RCLONE_SERVE_USER`  | `str`  | Serve username. |
| `RCLONE_SERVE_PASS`  | `str`  | Serve password. |

## 5. Update

| Variable         | Type  | Description |
|------------------|-------|-------------|
| `UPSTREAM_REPO`   | `str` | GitHub repo link. For private, use `https://username:token@github.com/username/repo`. [Get token](https://github.com/settings/tokens). |
| `UPSTREAM_BRANCH` | `str` | Branch to use. Default: `master`. |

## 6. Leech

| Variable                | Type            | Description |
|-------------------------|-----------------|-------------|
| `LEECH_SPLIT_SIZE`       | `int`           | Split size in bytes for leeching. Default: `2GB` (standard users), `4GB` (Telegram premium users). |
| `AS_DOCUMENT`            | `bool`          | Upload leeched files as documents. Default: `False` (uploads as media). |
| `USER_TRANSMISSION`      | `bool`          | Use user session for uploads/downloads in supergroups. Default: `False`. |
| `HYBRID_LEECH`           | `bool`          | Switch between bot and user sessions for leeching based on file size. Default: `False`. |
| `LEECH_DUMP_CHAT`        | `list[str/int]` | Chat/Channel ID(s) to send leeched files. Use `-100` prefix for private channels or `chat_id|thread_id` for topics. |
| `THUMBNAIL_LAYOUT`       | `str`           | Layout like `2x2`, `4x4`, `3x3`, etc. |

## 7. qBittorrent/Aria2c/Sabnzbd

| Variable           | Type   | Description |
|--------------------|--------|-------------|
| `TORRENT_TIMEOUT`   | `int`  | Timeout in seconds for dead torrents. |
| `BASE_URL`          | `str`  | Bot URL. Example: `http://myip` or `http://myip:port`. |
| `BASE_URL_PORT`     | `int`  | Port. Default: `80`. |
| `WEB_PINCODE`       | `bool` | Ask PIN before file selection. Default: `False`. |

## 8. JDownloader

| Variable     | Type  | Description |
|--------------|-------|-------------|
| `JD_EMAIL`    | `str` | Email for [My JDownloader](https://my.jdownloader.org/). |
| `JD_PASS`     | `str` | Password for My JDownloader. You may zip your `cfg/` directory as `cfg.zip` and include it in the repository. |

## 9. Sabnzbd

| Variable        | Type   | Description |
|-----------------|--------|-------------|
| `USENET_SERVERS` | `list` | List of dictionaries with Usenet server configurations. Example:
```
[{'name': 'main', 'host': '', 'port': 563, 'timeout': 60, 'username': '', 'password': '', 'connections': 8, 'ssl': 1, 'ssl_verify': 2, 'ssl_ciphers': '', 'enable': 1, 'required': 0, 'optional': 0, 'retention': 0, 'send_group': 0, 'priority': 0}]
```
[More info](https://sabnzbd.org/wiki/configuration/4.2/servers)

## 10. RSS

| Variable         | Type         | Description |
|------------------|--------------|-------------|
| `RSS_DELAY`       | `int`        | Time interval in seconds. Default: `600`. |
| `RSS_SIZE_LIMIT`  | `int`        | Max item size in bytes. Default: `0`. |
| `RSS_CHAT`        | `str`/`int`  | Chat ID or username. Use `channel|topic` format if needed. |

**Note:** `RSS_CHAT` is mandatory. Requires either `USER_SESSION_STRING` or linked group/channel setup.

## 11. Queue System

| Variable          | Type  | Description |
|-------------------|-------|-------------|
| `QUEUE_ALL`        | `int` | Max concurrent upload + download tasks. |
| `QUEUE_DOWNLOAD`   | `int` | Max concurrent download tasks. |
| `QUEUE_UPLOAD`     | `int` | Max concurrent upload tasks. |

## 12. NZB Search

| Variable         | Type  | Description |
|------------------|-------|-------------|
| `HYDRA_IP`        | `str` | IP address of [NZBHydra2](https://github.com/theotherp/nzbhydra2). |
| `HYDRA_API_KEY`   | `str` | API key from NZBHydra2. |

## 13. Aeon-Specific Configurations

| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `METADATA_KEY`         | `str`  | Key used to tag or fetch metadata. |
| `WATERMARK_KEY`        | `str`  | Key used for watermarking files or content. |
| `SET_COMMANDS`         | `bool` | Whether to register bot commands on startup. |
| `TOKEN_TIMEOUT`        | `int`  | Timeout in seconds for token/session expiry. |
| `PAID_CHANNEL_ID`      | `int`  | Telegram Channel ID that users must join to use the bot without a token. |
| `PAID_CHANNEL_LINK`    | `str`  | Public or invite link to the paid Telegram channel. |
| `DELETE_LINKS`         | `bool` | If `True`, automatically delete download or share links after a certain period or action. |
| `FSUB_IDS`             | `str`  | Comma-separated Chat IDs of channels users must subscribe to (forced subscription). |
| `LOG_CHAT_ID`          | `int`  | Chat ID where leech logs are sent. |
| `LEECH_FILENAME_CAPTION` | `str` | Template caption for leeched/downloaded filenames. |
| `INSTADL_API`          | `str`  | URL or endpoint for InstaDL API integration. |
| `HEROKU_APP_NAME`      | `str`  | Name of your Heroku app, used to get `BASE_URL` automatically. |
| `HEROKU_API_KEY`       | `str`  | API key for accessing and controlling your Heroku app. |
| `NAME_PREFIX`          | `str`  | Name prefix. |