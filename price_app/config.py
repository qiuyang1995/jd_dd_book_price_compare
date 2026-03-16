from pathlib import Path

APP_TITLE = "图书价格抓取工具（京东 + 当当）"
BASE_DIR = Path(__file__).resolve().parent.parent

# Playwright 持久化浏览器目录。
# 如需清空京东登录态，删除这个目录即可。
JD_BROWSER_PROFILE_DIR = BASE_DIR / ".playwright-jd-profile"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

JD_HOME_URL = "https://www.jd.com/"
JD_LOGIN_URL = "https://passport.jd.com/new/login.aspx"
JD_SEARCH_URL_TEMPLATE = "https://search.jd.com/Search?keyword={isbn}"

# 单次 HTTP 请求超时时间，单位秒。
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15

# 京东两次请求之间的基础等待时间，单位秒。
# 实际等待 = 基础时间 + 随机抖动 + 长时间运行后的附加惩罚。
DEFAULT_SLEEP_BASE_SECONDS = 15

# 基础抖动范围，单位秒。
# 当前配置表示正常情况下请求间隔落在 15-25 秒之间。
DEFAULT_SLEEP_JITTER_MIN_SECONDS = 0
DEFAULT_SLEEP_JITTER_MAX_SECONDS = 10

# 连续失败时，基础等待时间最多提升到这个值，单位秒。
MAX_SLEEP_BASE_SECONDS = 60

# 出现访问受限时，允许把基础等待时间进一步抬高到这个值，单位秒。
MAX_ACCESS_RESTRICTED_BASE_SECONDS = 120

# 每处理多少条记录自动保存一次 Excel。
AUTO_SAVE_INTERVAL = 5
