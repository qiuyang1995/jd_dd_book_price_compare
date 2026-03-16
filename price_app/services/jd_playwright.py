from __future__ import annotations

import random
import re
import time
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup, Tag

from price_app.config import JD_BROWSER_PROFILE_DIR, JD_HOME_URL, JD_LOGIN_URL, JD_SEARCH_URL_TEMPLATE
from price_app.models import JDPriceResult, JDQueryStatus

try:
    from playwright.sync_api import (
        BrowserContext,
        Page,
        Playwright,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError:  # pragma: no cover - 仅在未安装依赖时触发
    BrowserContext = Any
    Page = Any
    Playwright = Any
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


SELF_OPERATED_MARKERS = ("自营",)
NO_RESULT_MARKERS = ("抱歉，没有找到", "暂无报价", "未找到相关商品", "搜索无结果")
RESTRICTED_MARKERS = ("验证码", "安全验证", "请求过于频繁", "访问受限", "请稍后再试", "机器人")
LOGIN_MARKERS = ("账户登录", "扫码登录", "请登录", "用户登录")


def extract_self_operated_price_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for card in _iter_candidate_cards(soup):
        if not _is_self_operated_card(card):
            continue
        price = _extract_price_from_card(card)
        if price:
            return price
    return None


def page_has_no_results(html: str) -> bool:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return any(marker in text for marker in NO_RESULT_MARKERS)


def _iter_candidate_cards(soup: BeautifulSoup) -> list[Tag]:
    selectors = [
        "li[data-sku]",
        ".gl-item",
        "div[data-sku]",
        "._wrapper_f6icl_11 li",
        "._wrapper_f6icl_11 > div",
    ]
    unique_cards: list[Tag] = []
    seen_ids: set[int] = set()
    for selector in selectors:
        for tag in soup.select(selector):
            tag_id = id(tag)
            if tag_id in seen_ids:
                continue
            seen_ids.add(tag_id)
            unique_cards.append(tag)
    return unique_cards


def _is_self_operated_card(card: Tag) -> bool:
    text = card.get_text(" ", strip=True)
    if any(marker in text for marker in SELF_OPERATED_MARKERS):
        return True

    for image in card.find_all("img"):
        alt = str(image.get("alt", ""))
        title = str(image.get("title", ""))
        if any(marker in alt or marker in title for marker in SELF_OPERATED_MARKERS):
            return True

    return False


def _extract_price_from_card(card: Tag) -> str | None:
    selectors = [
        "span._price_uqsva_14",
        ".p-price",
        "[class*='price']",
        "strong",
        "em",
    ]

    for selector in selectors:
        for node in card.select(selector):
            price = _extract_price_from_text(node.get_text(" ", strip=True))
            if price:
                return price

    html = str(card)
    currency_match = re.search(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)", html)
    if currency_match:
        return currency_match.group(1)
    return None


def _extract_price_from_text(text: str) -> str | None:
    normalized = re.sub(r"\s+", "", text).replace("¥", "").replace("￥", "")
    if not normalized:
        return None

    decimal_match = re.search(r"(\d+\.\d{1,2})", normalized)
    if decimal_match:
        return decimal_match.group(1)

    if normalized.isdigit() and len(normalized) <= 5:
        return normalized
    return None


class JDPlaywrightService:
    """负责京东浏览器会话、登录保持和价格抓取。"""

    def __init__(
        self,
        profile_dir: str | Path = JD_BROWSER_PROFILE_DIR,
        log_callback: Callable[[str], None] | None = None,
        headless: bool = False,
    ):
        self.profile_dir = Path(profile_dir)
        self.log_callback = log_callback
        self.headless = headless
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.request_count = 0

    def __enter__(self) -> "JDPlaywrightService":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> None:
        if self.page is not None:
            return
        if sync_playwright is None:
            raise RuntimeError("未安装 playwright，请先执行 `pip install -r requirements.txt`。")

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = sync_playwright().start()

        launch_options: dict[str, Any] = {
            "headless": self.headless,
            "viewport": {"width": 1440, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        }

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="chrome",
                **launch_options,
            )
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                raise RuntimeError(
                    "Playwright 浏览器未安装，请先执行 `python -m playwright install chromium`。"
                ) from exc
            self._log("⚠️ 未检测到本机 Chrome，回退到 Playwright Chromium。")
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                **launch_options,
            )

        self.context.set_extra_http_headers({"User-Agent": self._build_user_agent()})
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None
        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None
        self.page = None

    def ensure_login(self, confirm_login: Callable[[], bool]) -> bool:
        self.start()
        assert self.page is not None

        self._goto_with_retry(JD_HOME_URL)
        if self._wait_until_logged_in(timeout_ms=3_000):
            self._log("✅ 已检测到京东登录态。")
            return True

        self._log("🔑 需要人工扫码登录京东。")
        while True:
            self._goto_with_retry(JD_LOGIN_URL)
            if confirm_login():
                break

        # 扫码成功后京东通常会自动跳转，这里优先等待页面自然稳定，
        # 避免与站点自身的跳转竞争导致 navigation interrupted。
        if self._wait_until_logged_in(timeout_ms=30_000):
            self._log("✅ 京东登录成功，登录态将由 Playwright 持久化保存。")
            return True

        self._goto_with_retry(JD_HOME_URL)
        if self._wait_until_logged_in(timeout_ms=5_000):
            self._log("✅ 京东登录成功，登录态将由 Playwright 持久化保存。")
            return True

        self._log("❌ 未检测到有效登录态。")
        return False

    def fetch_price(self, isbn: str) -> JDPriceResult:
        self.start()
        assert self.page is not None

        self.request_count += 1
        search_url = JD_SEARCH_URL_TEMPLATE.format(isbn=isbn)
        self._log(f"🔍 京东搜索 ISBN: {isbn}")

        try:
            for attempt in range(3):
                self._goto_with_retry(search_url, extra_wait_ms=2_000 + attempt * 800)
                self._simulate_reading_behavior()

                if self._is_login_page():
                    return JDPriceResult(JDQueryStatus.LOGIN_REQUIRED, message="登录失败")
                if self._is_access_restricted():
                    return JDPriceResult(JDQueryStatus.ACCESS_RESTRICTED, message="访问受限")

                html = self.page.content()
                price = extract_self_operated_price_from_html(html)
                if price:
                    return JDPriceResult(JDQueryStatus.SUCCESS, price=price)
                if page_has_no_results(html):
                    return JDPriceResult(JDQueryStatus.NOT_FOUND, message="未找到商品")

            return JDPriceResult(JDQueryStatus.NO_SELF_OPERATED, message="无自营")
        except PlaywrightTimeoutError:
            return JDPriceResult(JDQueryStatus.TIMEOUT, message="超时")
        except Exception as exc:
            return JDPriceResult(JDQueryStatus.ERROR, message=f"错误: {exc}")

    def _goto_with_retry(self, url: str, extra_wait_ms: int = 1_500) -> None:
        assert self.page is not None
        last_error: Exception | None = None

        for _ in range(2):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                self.page.wait_for_timeout(extra_wait_ms)
                return
            except Exception as exc:  # noqa: BLE001 - 需要统一兜住 Playwright 导航异常
                last_error = exc
                if "interrupted by another navigation" not in str(exc):
                    raise

                self._log("⚠️ 检测到页面正在自动跳转，等待页面稳定后继续。")
                self._wait_for_page_stable(timeout_ms=8_000)
                if self.page.url.startswith(url):
                    self.page.wait_for_timeout(extra_wait_ms)
                    return

        if last_error is not None:
            raise last_error

    def _wait_until_logged_in(self, timeout_ms: int) -> bool:
        assert self.page is not None
        deadline = timeout_ms / 1000
        start_time = time.time()

        while time.time() - start_time < deadline:
            self._wait_for_page_stable(timeout_ms=3_000)
            try:
                if self._is_logged_in():
                    return True
            except Exception:
                pass
            self.page.wait_for_timeout(800)
        return False

    def _wait_for_page_stable(self, timeout_ms: int) -> None:
        assert self.page is not None
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            return

    def _is_logged_in(self) -> bool:
        if self._is_login_page():
            return False
        assert self.page is not None
        body_text = self.page.locator("body").inner_text(timeout=5_000)
        return "你好，请登录" not in body_text

    def _is_login_page(self) -> bool:
        assert self.page is not None
        current_url = self.page.url.lower()
        if any(keyword in current_url for keyword in ("passport.jd.com", "login.jd.com", "/login")):
            return True

        title = self.page.title().lower()
        if any(keyword.lower() in title for keyword in LOGIN_MARKERS):
            return True

        body_text = self.page.locator("body").inner_text(timeout=5_000).lower()
        return any(keyword.lower() in body_text for keyword in LOGIN_MARKERS)

    def _is_access_restricted(self) -> bool:
        assert self.page is not None
        title = self.page.title()
        body_text = self.page.locator("body").inner_text(timeout=5_000)
        text = f"{title}\n{body_text}"
        return any(marker in text for marker in RESTRICTED_MARKERS)

    def _simulate_reading_behavior(self) -> None:
        """只保留轻量随机滚动，避免把副作用混进主流程。"""
        assert self.page is not None
        try:
            if random.random() < 0.6:
                self.page.mouse.wheel(0, random.randint(120, 360))
                self.page.wait_for_timeout(random.randint(400, 900))
                self.page.mouse.wheel(0, -random.randint(80, 220))
        except Exception:
            return

    @staticmethod
    def _build_user_agent() -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )

    def _log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)
