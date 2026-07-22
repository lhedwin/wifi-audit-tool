import unittest
import time

import auditar_wifi


class TestHashcatStatusParsing(unittest.TestCase):
    def test_top_level_hashes_are_used_when_progress_is_missing(self):
        payload = {
            "hashes_done": 2500,
            "hashes_total": 100000,
            "speed": {"0": {"rate": 1000}},
            "estimated_stop": time.time() + 120,
            "status": 0,
        }

        parsed = auditar_wifi.parse_hashcat_status(payload)
        self.assertAlmostEqual(parsed["pct"], 2.5)
        self.assertEqual(parsed["hashes_cur"], 2500)
        self.assertEqual(parsed["hashes_end"], 100000)
        self.assertEqual(parsed["speed_val"], 1000)

    def test_list_speed_and_nested_progress_are_supported(self):
        payload = {
            "progress": {"cur": 10, "end": 1000, "percent": 0.01},
            "speed": [{"rate": 5000}],
            "estimated_stop": time.time() + 60,
            "status": 0,
        }

        parsed = auditar_wifi.parse_hashcat_status(payload)
        self.assertAlmostEqual(parsed["pct"], 1.0)
        self.assertEqual(parsed["hashes_cur"], 10)
        self.assertEqual(parsed["hashes_end"], 1000)
        self.assertEqual(parsed["speed_val"], 5000)


if __name__ == "__main__":
    unittest.main()
