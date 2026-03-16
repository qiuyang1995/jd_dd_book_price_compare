import unittest

from price_app.services.dangdang import extract_discount_text, parse_search_listing


class DangDangParserTests(unittest.TestCase):
    def test_parse_search_listing_extracts_price_and_product_id(self) -> None:
        html = """
        <div id="search_nature_rg" dd_name="普通商品区域">
            <li sku="29384756">
                <span class="search_now_price">¥29.80</span>
            </li>
        </div>
        """
        listing = parse_search_listing(html)
        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertEqual(listing.price, "29.80")
        self.assertEqual(listing.product_id, "29384756")
        self.assertTrue(listing.in_stock)

    def test_parse_search_listing_handles_arrival_notice(self) -> None:
        html = """
        <div id="search_nature_rg" dd_name="普通商品区域">
            <li sku="29384756">
                <a class="search_btn_cart" name="pdno">到货通知</a>
            </li>
        </div>
        """
        listing = parse_search_listing(html)
        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertFalse(listing.in_stock)
        self.assertEqual(listing.price, "")

    def test_extract_discount_text_ignores_coupon_and_self_operated(self) -> None:
        payload = {
            "29384756": [
                {"label_name": "自营"},
                {"label_name": "满100减20"},
                {"label_name": "券"},
                {"label_name": "每满50减5"},
            ]
        }
        self.assertEqual(extract_discount_text(payload, "29384756"), "满100减20，每满50减5")


if __name__ == "__main__":
    unittest.main()

