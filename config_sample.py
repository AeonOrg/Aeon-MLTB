# REQUIRED CONFIG
BOT_TOKEN = ""
OWNER_ID = 0
TELEGRAM_API = 0
TELEGRAM_HASH = ""

# Recommended for persisting settings, RSS feeds, and task history. Essential for some features.
DATABASE_URL = ""

# OPTIONAL CONFIG
TG_PROXY = {}  # Example: {"scheme": "socks5", "hostname": "11.22.33.44", "port": 1234, "username": "user", "password": "pass"}
USER_SESSION_STRING = ""
CMD_SUFFIX = ""  # Suffix to add to all bot commands
AUTHORIZED_CHATS = ""  # Space separated chat_id/user_id to authorize
SUDO_USERS = ""  # Space separated user_id for sudo access
DEFAULT_UPLOAD = ""  # Default uploader if -ul is not specified. Options: "yt" (YouTube), "gd" (Google Drive), "rc" (Rclone), "gofile" (GoFile), or "" (empty for no specific default).
FILELION_API = ""
GOFILE_API = ""  # GoFile API token for uploading files to GoFile.io (get from https://gofile.io/myProfile)
STREAMWISH_API = ""
EXCLUDED_EXTENSIONS = (
    ""  # Space separated file extensions to exclude (e.g., .log .exe)
)
INCOMPLETE_TASK_NOTIFIER = (
    False  # Notify for incomplete tasks on restart (requires DATABASE_URL)
)
YT_DLP_OPTIONS = {}  # Dictionary of yt-dlp options, e.g., {"format": "bestvideo+bestaudio/best"}
USE_SERVICE_ACCOUNTS = False
NAME_SUBSTITUTE = ""  # Replace/remove words: "source1/target1|source2/target2"
FFMPEG_CMDS = {}  # Predefined FFmpeg commands, e.g., {"preset_name": ["-vf", "scale=1280:-1"]}
UPLOAD_PATHS = {}  # Named upload paths, e.g., {"movies": "remote:movies/", "tv": "gdrive_id_tv_folder"}

# Aeon-MLTB Specific Features / Customizations
DELETE_LINKS = False  # Auto-delete links after a certain period or action
FSUB_IDS = ""  # Forced subscription channel IDs (comma-separated)
TOKEN_TIMEOUT = 0  # Timeout in seconds for user tokens (0 for no timeout)
PAID_CHANNEL_ID = 0  # Channel ID users must join to bypass token
PAID_CHANNEL_LINK = ""  # Invite link for the paid channel
SET_COMMANDS = True  # Register bot commands with BotFather on startup
METADATA_KEY = ""  # Key for tagging/fetching metadata
WATERMARK_KEY = ""  # Key for watermarking files
LOG_CHAT_ID = 0  # Chat ID for sending leech logs
LEECH_FILENAME_CAPTION = ""  # Template caption for leeched files
HYDRA_IP = ""  # IP of NZBHydra2 instance
HYDRA_API_KEY = ""  # API key for NZBHydra2
INSTADL_API = ""  # URL/endpoint for InstaDL API

# GDrive Tools
GDRIVE_ID = ""  # Default Google Drive Folder/TeamDrive ID or "root"
IS_TEAM_DRIVE = False  # Set True if GDRIVE_ID is a TeamDrive
STOP_DUPLICATE = False  # Check for duplicate file/folder names before uploading
INDEX_URL = ""  # Index URL for the GDrive_ID

# Rclone
RCLONE_PATH = ""  # Default Rclone upload path (e.g., myremote:path)
RCLONE_FLAGS = ""  # Additional Rclone flags (e.g., --drive-chunk-size=64M)
RCLONE_SERVE_URL = ""  # URL for Rclone serve (e.g., http://myip or http://myip:port)
RCLONE_SERVE_PORT = 8080  # Port for Rclone serve (Default: 8080)
RCLONE_SERVE_USER = ""  # Username for Rclone serve
RCLONE_SERVE_PASS = ""  # Password for Rclone serve

# Sabnzbd
USENET_SERVERS = [  # List of Usenet server configurations
    {
        "name": "main",  # Server name
        "host": "",  # Server host
        "port": 563,  # Server port (e.g., 563 for SSL, 119 for non-SSL)
        "timeout": 60,  # Connection timeout in seconds
        "username": "",  # Server username
        "password": "",  # Server password
        "connections": 8,  # Number of connections
        "ssl": 1,  # SSL usage: 0=None, 1=SSL, 2=TLS
        "ssl_verify": 2,  # SSL verification: 0=None, 1=Warn, 2=Abort
        "ssl_ciphers": "",  # Custom SSL ciphers
        "enable": 1,  # Enable this server: 1=Yes, 0=No
        "required": 0,  # Required server: 1=Yes, 0=No
        "optional": 0,  # Optional server: 1=Yes, 0=No
        "retention": 0,  # Server retention in days (0 for unknown)
        "send_group": 0,  # Send group names: 1=Yes, 0=No
        "priority": 0,  # Server priority (0-100, lower is higher priority)
    },
]

# Update
UPSTREAM_REPO = (
    "https://github.com/AeonOrg/Aeon-MLTB"  # Upstream repository for updates
)
UPSTREAM_BRANCH = "main"  # Default branch for updates

# Leech
LEECH_SPLIT_SIZE = 2097152000  # Split size for leeched files in bytes. Default: 2GB. Max: 4GB for Premium, 2GB for others. 0 for bot default.
AS_DOCUMENT = False  # Upload leeched files as documents instead of media
MEDIA_GROUP = False  # Send leeched files as a media group
USER_TRANSMISSION = False  # Use user session for uploads/downloads (Premium only)
HYBRID_LEECH = (
    False  # Switch between bot/user session based on file size (Premium only)
)
LEECH_FILENAME_PREFIX = ""  # Prefix for leeched filenames
LEECH_DUMP_CHAT = []  # List of chat_ids or channel_ids to dump leeched files, e.g., [-100123456789, "channel_username"]
THUMBNAIL_LAYOUT = ""  # Thumbnail layout for uploads (e.g., 2x2, 3x3)

# qBittorrent/Aria2c
TORRENT_TIMEOUT = 0  # Timeout in seconds for dead torrents. 0 for no timeout.
BASE_URL = ""  # Base URL of the bot, for web file selection (e.g., http://myip or http://myip:port)
BASE_URL_PORT = 80  # Port for the BASE_URL (Default: 80)
WEB_PINCODE = False  # Require a PIN code for web file selection

# Queueing system
QUEUE_ALL = 0  # Max concurrent tasks (upload + download)
QUEUE_DOWNLOAD = 0  # Max concurrent download tasks
QUEUE_UPLOAD = 0  # Max concurrent upload tasks

# RSS
RSS_DELAY = 600  # RSS feed check interval in seconds (Default: 600)
RSS_CHAT = ""  # Chat ID or username where RSS messages will be sent
RSS_SIZE_LIMIT = 0  # Max size for RSS items in bytes (0 for no limit)

# Heroku config for get BASE_URL automatically
HEROKU_APP_NAME = ""  # Name of your Heroku app, used to get BASE_URL automatically
HEROKU_API_KEY = ""  # API key for your Heroku account
