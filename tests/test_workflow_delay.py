import unittest
from unittest.mock import patch

from price_app.models import JDPriceResult, JDQueryStatus
from price_app.services.workflow import AdaptiveDelayController


class AdaptiveDelayControllerTests(unittest.TestCase):
    def test_default_delay_is_between_15_and_25_seconds(self) -> None:
        controller = AdaptiveDelayController()

        with patch("price_app.services.workflow.random.uniform", return_value=0):
            self.assertEqual(controller.next_delay_seconds(), 15)

        with patch("price_app.services.workflow.random.uniform", return_value=10):
            self.assertEqual(controller.next_delay_seconds(), 25)

    def test_error_response_increases_base_delay(self) -> None:
        controller = AdaptiveDelayController()
        controller.observe(JDPriceResult(status=JDQueryStatus.TIMEOUT, message="超时"))

        with patch("price_app.services.workflow.random.uniform", return_value=0):
            self.assertEqual(controller.next_delay_seconds(), 20)


if __name__ == "__main__":
    unittest.main()
