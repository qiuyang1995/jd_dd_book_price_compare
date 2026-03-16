import unittest

from price_app.services.jd_playwright import extract_self_operated_price_from_html, page_has_no_results


class JDHtmlParserTests(unittest.TestCase):
    def test_extract_self_operated_price_from_html(self) -> None:
        html = """
        <div class="_wrapper_f6icl_11">
            <li data-sku="1">
                <div class="_imgTag_1qbwk_1"><img alt="自营" /></div>
                <span class="_price_uqsva_14">249<span>.</span><span>5</span></span>
            </li>
            <li data-sku="2">
                <span class="_price_uqsva_14">199.00</span>
            </li>
        </div>
        """
        self.assertEqual(extract_self_operated_price_from_html(html), "249.5")

    def test_page_has_no_results(self) -> None:
        html = "<html><body><div>抱歉，没有找到与您的搜索相关的商品</div></body></html>"
        self.assertTrue(page_has_no_results(html))


if __name__ == "__main__":
    unittest.main()
