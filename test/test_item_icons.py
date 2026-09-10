import base64
import os
import tempfile
import unittest
from unittest.mock import Mock

from app import champions


class ItemIconTests(unittest.TestCase):
    """装备图标：客户端优先、本机缓存、CDN 兜底（CDN 不可达时详情仍能显示）。"""

    def setUp(self):
        champions._item_icons.clear()
        champions._item_paths = None
        champions._item_map_port = None
        champions._item_map_attempt = None
        self._old_localappdata = os.environ.get("LOCALAPPDATA")
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name

    def tearDown(self):
        if self._old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old_localappdata
        self._tmp.cleanup()

    def test_prefers_client_icon_and_caches_in_memory(self):
        lcu = Mock(port=123)
        lcu.request.return_value = (200, [
            {"id": 3157, "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/3157.png"},
            {"id": 3089, "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/3089.png"}])
        lcu.asset_data_url.return_value = "data:image/png;base64,QUJD"
        self.assertEqual(champions.item_icon(3157, lcu), "data:image/png;base64,QUJD")
        self.assertEqual(champions.item_icon(3089, lcu), "data:image/png;base64,QUJD")
        lcu.request.assert_called_once()  # items.json 每个客户端只取一次
        self.assertEqual(lcu.asset_data_url.call_count, 2)
        # 客户端断开后仍由内存缓存提供
        self.assertEqual(champions.item_icon(3157, None), "data:image/png;base64,QUJD")

    def test_persists_icon_to_localappdata(self):
        lcu = Mock(port=123)
        lcu.request.return_value = (200, [
            {"id": 3089, "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/3089.png"}])
        png = base64.b64encode(b"\x89PNG\r\n\x1a\nfake icon").decode("ascii")
        lcu.asset_data_url.return_value = "data:image/png;base64," + png
        champions.item_icon(3089, lcu)
        champions._item_icons.clear()  # 模拟重启
        self.assertEqual(champions.item_icon(3089, None), lcu.asset_data_url.return_value)

    def test_falls_back_to_cdn_without_client(self):
        self.assertEqual(champions.item_icon(3089, None),
                         "https://game.gtimg.cn/images/lol/act/img/item/3089.png")

    def test_invalid_ids(self):
        self.assertEqual(champions.item_icon(0), "")
        self.assertEqual(champions.item_icon(-5), "")
        self.assertEqual(champions.item_icon(None), "")
        self.assertEqual(champions.item_icon("abc"), "")


if __name__ == "__main__":
    unittest.main()
