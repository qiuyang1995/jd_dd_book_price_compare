from __future__ import annotations

import random
import time
from typing import Callable

from price_app.config import (
    AUTO_SAVE_INTERVAL,
    DEFAULT_SLEEP_BASE_SECONDS,
    DEFAULT_SLEEP_JITTER_MAX_SECONDS,
    DEFAULT_SLEEP_JITTER_MIN_SECONDS,
    MAX_ACCESS_RESTRICTED_BASE_SECONDS,
    MAX_SLEEP_BASE_SECONDS,
)
from price_app.excel_service import ExcelPriceWorkbook
from price_app.models import JDPriceResult, JDQueryStatus, RunSummary
from price_app.services.dangdang import DangDangPriceService
from price_app.services.jd_playwright import JDPlaywrightService


class AdaptiveDelayController:
    """根据京东返回状态动态调节请求节奏。"""

    def __init__(self, base_seconds: int = DEFAULT_SLEEP_BASE_SECONDS):
        self.base_seconds = base_seconds
        self.request_count = 0

    def observe(self, jd_result: JDPriceResult) -> None:
        self.request_count += 1
        if jd_result.status in {
            JDQueryStatus.ACCESS_RESTRICTED,
            JDQueryStatus.LOGIN_REQUIRED,
            JDQueryStatus.TIMEOUT,
            JDQueryStatus.ERROR,
        }:
            self.base_seconds = min(self.base_seconds + 5, MAX_SLEEP_BASE_SECONDS)
            return

        if jd_result.is_success and self.base_seconds > DEFAULT_SLEEP_BASE_SECONDS:
            self.base_seconds = max(self.base_seconds - 1, DEFAULT_SLEEP_BASE_SECONDS)

    def penalize_access_restriction(self) -> None:
        self.base_seconds = min(self.base_seconds + 10, MAX_ACCESS_RESTRICTED_BASE_SECONDS)

    def next_delay_seconds(self) -> int:
        additional = min((self.request_count // 20) * 5, 40)
        jitter = random.uniform(DEFAULT_SLEEP_JITTER_MIN_SECONDS, DEFAULT_SLEEP_JITTER_MAX_SECONDS)
        return int(self.base_seconds + additional + jitter)


class PriceWorkflow:
    def __init__(
        self,
        jd_service: JDPlaywrightService,
        dd_service: DangDangPriceService,
        log_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        confirm_login: Callable[[], bool] | None = None,
        auto_save_interval: int = AUTO_SAVE_INTERVAL,
    ):
        self.jd_service = jd_service
        self.dd_service = dd_service
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.confirm_login = confirm_login or (lambda: False)
        self.auto_save_interval = auto_save_interval
        self.delay_controller = AdaptiveDelayController()

    def process(self, file_path: str) -> RunSummary:
        workbook = ExcelPriceWorkbook(file_path)
        total = workbook.total_rows
        if total == 0:
            raise ValueError("Excel 中未找到有效的 ISBN 数据。")

        start_time = time.time()
        processed = 0
        self._update_progress(0, total)

        if not self.jd_service.ensure_login(self.confirm_login):
            raise RuntimeError("京东登录失败，请确认浏览器中已完成扫码登录。")

        try:
            for row in workbook.iter_isbn_rows():
                jd_result = self.jd_service.fetch_price(row.isbn)
                if jd_result.status == JDQueryStatus.LOGIN_REQUIRED:
                    workbook.save()
                    raise RuntimeError("检测到京东登录失效，请重新登录后重试。")

                if jd_result.status == JDQueryStatus.ACCESS_RESTRICTED:
                    self.delay_controller.penalize_access_restriction()
                    self._log("⚠️ 京东返回访问受限，已自动提高请求间隔。")

                self.delay_controller.observe(jd_result)
                dd_result = self.dd_service.fetch_price(row.isbn)
                workbook.write_result(
                    row_index=row.row_index,
                    jd_price=jd_result.display_value,
                    dd_price=dd_result.price,
                    dd_discount=dd_result.discount,
                )

                processed += 1
                if processed % self.auto_save_interval == 0:
                    workbook.save()
                    self._log("💾 已自动保存当前进度。")

                delay_seconds = self.delay_controller.next_delay_seconds()
                self._update_progress(processed, total)
                self._log(
                    f"{processed}/{total} ✅ {row.isbn} → 京东 ¥{jd_result.display_value or '未获取'} "
                    f"| 当当 ¥{dd_result.price or '未获取'} {dd_result.discount}".rstrip()
                )

                if processed < total:
                    self._log(f"⏳ 等待 {delay_seconds} 秒后继续下一条。")
                    time.sleep(delay_seconds)
        finally:
            workbook.save()

        return RunSummary(
            processed_rows=processed,
            total_rows=total,
            elapsed_seconds=time.time() - start_time,
        )

    def _log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)

    def _update_progress(self, current: int, total: int) -> None:
        if self.progress_callback is not None:
            self.progress_callback(current, total)
