"""Cấu hình dạng dict thuần — vòng tròn đầy đủ từ sóng về sóng.

Chuỗi được kiểm ở đây là toàn bộ giai đoạn T2:

    dump từ sóng → mô hình → cấu hình → mô hình → XML → so lại với dump

Đi trọn vòng mà không mất gì nghĩa là **cấu hình đủ để tái tạo sóng**, và có
thể vứt bản dump đi sau khi gieo. Đó chính là điều phân biệt *gieo một lần* với
*soi liên tục*.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from vtcsi.model import plain
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"


def _require() -> str:
    if not GOLDEN.exists():
        raise unittest.SkipTest("khong tim thay chuan vang")
    return GOLDEN.read_text(encoding="utf-8")


class TestFullCircle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _require()
        cls.root = ET.fromstring(cls.text)
        cls.from_air = T.read_dump(cls.text)
        cls.cfg_dict = plain.to_plain(cls.from_air)
        cls.rebuilt = plain.from_plain(cls.cfg_dict)

    def test_model_survives_the_round_trip(self) -> None:
        self.assertEqual(self.rebuilt.network, self.from_air.network)
        self.assertEqual(self.rebuilt.sdts, self.from_air.sdts)
        self.assertEqual(self.rebuilt.bouquets, self.from_air.bouquets)

    def test_xml_rebuilt_from_config_still_matches_the_air(self) -> None:
        """Vòng dài nhất: cấu hình sinh ra XML khớp đúng bản dump gốc."""
        nit = self.root.find("NIT")
        self.assertEqual(T.canon(T.write_nit(self.rebuilt.network)), T.canon(nit))

        for sdt in self.rebuilt.sdts:
            with self.subTest(ts=sdt.ts_id):
                orig = next(e for e in self.root.findall("SDT")
                            if T.num(e.get("transport_stream_id")) == sdt.ts_id)
                self.assertEqual(T.canon(T.write_sdt(sdt)), T.canon(orig))

        for b in self.rebuilt.bouquets:
            with self.subTest(bouquet=hex(b.bouquet_id)):
                orig = next(e for e in self.root.findall("BAT")
                            if T.num(e.get("bouquet_id")) == b.bouquet_id)
                self.assertEqual(T.canon(T.write_bat(b)), T.canon(orig))

    def test_to_plain_is_deterministic(self) -> None:
        for _ in range(10):
            self.assertEqual(plain.to_plain(self.from_air), self.cfg_dict)

    def test_config_holds_no_service_list(self) -> None:
        """FR-3: service_list không nằm trong cấu hình, nó được suy ra.

        Nếu bài này đỏ thì ai đó đã đưa danh sách ấy trở lại chỗ gõ tay được —
        và cái bẫy 'thêm kênh vào SDT nhưng quên NIT' quay lại theo.
        """
        for ts in self.cfg_dict["network"]["transport_streams"]:
            self.assertNotIn("service_list", ts)
            self.assertNotIn("services_in_nit", ts)

    def test_derived_service_list_matches_the_air(self) -> None:
        """Danh sách suy ra phải trùng cả tập, thứ tự lẫn service_type."""
        air = {loop.ts_id: loop.services for loop in self.from_air.network.ts_loops}
        for loop in self.rebuilt.network.ts_loops:
            with self.subTest(ts=loop.ts_id):
                self.assertEqual(loop.services, air[loop.ts_id])


class TestConfigShape(unittest.TestCase):
    """Cấu hình phải đọc được bằng mắt, vì người sẽ sửa nó bằng tay."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.d = plain.to_plain(T.read_dump(_require()))

    def test_one_entry_per_transport_stream(self) -> None:
        streams = self.d["network"]["transport_streams"]
        self.assertEqual([t["ts_id"] for t in streams], [3, 1000, 8])
        ts8 = next(t for t in streams if t["ts_id"] == 8)
        self.assertEqual(len(ts8["services"]), 64)
        self.assertTrue(ts8["actual"])
        self.assertEqual(ts8["sdt_version"], 9)
        self.assertEqual(ts8["delivery"]["frequency_hz"], 10_968_000_000)
        self.assertEqual(ts8["delivery"]["fec_inner"], "3/4")

    def test_ids_use_the_notation_people_speak(self) -> None:
        """Bouquet và linkage nói bằng hex, kênh và TS nói bằng thập phân."""
        b = self.d["bouquets"][0]
        self.assertTrue(str(b["bouquet_id"]).startswith("0x"))
        ts8 = next(t for t in self.d["network"]["transport_streams"] if t["ts_id"] == 8)
        self.assertIsInstance(ts8["services"][0]["service_id"], int)

    def test_bouquet_membership_is_just_a_list_of_ids(self) -> None:
        """service_type trong BAT cũng suy từ SDT, không lặp lại trong cấu hình."""
        b = next(x for x in self.d["bouquets"] if x["bouquet_id"] == "0x6510")
        loop = b["transport_streams"][0]
        self.assertTrue(all(isinstance(s, int) for s in loop["services"]))

    def test_lcn_lives_on_the_bouquet(self) -> None:
        b = next(x for x in self.d["bouquets"] if x["bouquet_id"] == "0x6510")
        total = sum(len(t["lcn"]) for t in b["transport_streams"])
        self.assertEqual(total, 78)
        ts8 = next(t for t in self.d["network"]["transport_streams"] if t["ts_id"] == 8)
        self.assertNotIn("lcn", ts8["services"][0])

    def test_private_data_is_readable_hex(self) -> None:
        lk = [x for x in self.d["network"]["linkages"] if x["linkage_type"] == "0x92"]
        self.assertEqual(len(lk), 1)
        self.assertEqual(lk[0]["private_data"],
                         "FF 04 FF 04 FF 00 FF 01 FF 30 32 35 32 FF 02")


class TestConfigRefusesBadInput(unittest.TestCase):
    def test_missing_required_field(self) -> None:
        with self.assertRaises(plain.ConfigError):
            plain.from_plain({"network": {"network_id": 1}})

    def test_bouquet_naming_a_service_that_does_not_exist(self) -> None:
        """Bẫy thật: gán kênh vào bouquet mà kênh đó không có trên TS."""
        d = plain.to_plain(T.read_dump(_require()))
        b = next(x for x in d["bouquets"] if x["bouquet_id"] == "0x6510")
        b["transport_streams"][0]["services"].append(9999)
        with self.assertRaises(plain.ConfigError):
            plain.from_plain(d)

    def test_accepts_both_hex_and_decimal_ids(self) -> None:
        d = plain.to_plain(T.read_dump(_require()))
        a = plain.from_plain(d)
        d["bouquets"][0]["bouquet_id"] = int(str(d["bouquets"][0]["bouquet_id"]), 16)
        self.assertEqual(plain.from_plain(d).bouquets[0], a.bouquets[0])


if __name__ == "__main__":
    unittest.main()
