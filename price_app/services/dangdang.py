from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

from price_app.config import DEFAULT_REQUEST_TIMEOUT_SECONDS, USER_AGENT
from price_app.models import DDPriceResult


@dataclass(frozen=True)
class DangDangSearchListing:
    price: str
    product_id: str | None
    in_stock: bool


def parse_search_listing(html: str) -> DangDangSearchListing | None:
    soup = BeautifulSoup(html, "html.parser")
    search_area = soup.find("div", {"id": "search_nature_rg", "dd_name": "普通商品区域"})
    if search_area is None:
        return None

    first_item = search_area.find("li")
    if first_item is None:
        return None

    arrival_notice = first_item.find("a", {"class": "search_btn_cart", "name": "pdno"})
    if arrival_notice and "到货通知" in arrival_notice.get_text(strip=True):
        return DangDangSearchListing(price="", product_id=None, in_stock=False)

    price_tag = first_item.find("span", {"class": "search_now_price"})
    price = ""
    if price_tag is not None:
        price = price_tag.get_text(strip=True).replace("¥", "").replace("&yen;", "")

    product_id = first_item.get("sku")
    if not product_id:
        product_link = first_item.find("a", {"class": "pic"})
        href = "" if product_link is None else str(product_link.get("href", ""))
        match = re.search(r"product\.dangdang\.com/(\d+)\.html", href)
        if match:
            product_id = match.group(1)

    return DangDangSearchListing(price=price, product_id=product_id, in_stock=True)


def extract_discount_text(payload: dict[str, Any], product_id: str) -> str:
    promotions = payload.get(product_id, [])
    labels = [item["label_name"] for item in promotions if item.get("label_name") not in {"自营", "券"}]
    return "，".join(labels) if labels else "无"


class DangDangPriceService:
    def __init__(self, session: requests.Session | None = None, timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.headers = {"User-Agent": USER_AGENT}

    def fetch_price(self, isbn: str) -> DDPriceResult:
        search_url = (
            "https://search.dangdang.com/"
            f"?key={isbn}&act=input&filter=0%7C0%7C0%7C0%7C0%7C1%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0"
        )

        try:
            response = self.session.get(search_url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return DDPriceResult()

        listing = parse_search_listing(response.text)
        if listing is None or not listing.in_stock:
            return DDPriceResult()
        if not listing.product_id:
            return DDPriceResult(price=listing.price, discount="")

        discount = self._fetch_discount_text(
            search_url=search_url,
            isbn=isbn,
            product_id=listing.product_id,
            cookies=response.cookies.get_dict(),
            set_cookie=response.headers.get("Set-Cookie", ""),
        )
        return DDPriceResult(price=listing.price, discount=discount)

    def _fetch_discount_text(
        self,
        search_url: str,
        isbn: str,
        product_id: str,
        cookies: dict[str, str],
        set_cookie: str,
    ) -> str:
        promo_url = (
            "https://search.dangdang.com/Standard/Search/Extend/hosts/api/get_json.php"
            f"?type=promoIcon&keys={product_id}"
            f"&url=0%2F%3Fkey%3D{isbn}%26act%3Dinput%26filter%3D0%7C0%7C0%7C0%7C0%7C1%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0"
            "&c=false&l=7b2eea5e6454245e9e56ac31ae24f124"
        )
        search_passback = self._extract_search_passback(cookies, set_cookie)
        if search_passback:
            cookies = {**cookies, "search_passback": search_passback}

        try:
            response = self.session.get(
                promo_url,
                headers={"Referer": search_url, "User-Agent": USER_AGENT},
                cookies=cookies,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return extract_discount_text(response.json(), product_id)
        except (requests.RequestException, ValueError):
            return ""

    @staticmethod
    def _extract_search_passback(cookies: dict[str, str], set_cookie: str) -> str:
        if "search_passback" in cookies:
            return cookies["search_passback"]
        match = re.search(r"search_passback=([^;]+)", set_cookie)
        return match.group(1) if match else ""
