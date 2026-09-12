"""Cấu hình trên đĩa — ghi ra nhiều file, đọc lại, vẫn tái tạo đúng sóng.

Đây là mắt xích cuối của giai đoạn T2. Chuỗi đầy đủ giờ là::

    dump từ sóng → mô hình → file YAML trong git → mô hình → XML ≡ dump

Từ đây trở đi bản dump chỉ còn để đối chiếu; thứ chạy hệ thống là các file
trong ``config/``.
"""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import seed
from vtcsi.config import loader
from vtcsi.model.plain import ConfigError
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"


def _require() -> str:
    if not GOLDEN.exists():
        raise unittest.SkipTest("khong tim thay chuan vang")
    return GOLDEN.read_text(encoding="utf-8")


class TestSaveLoad(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _require()
        cls.root_xml = ET.fromstring(cls.text)
        cls.from_air = T.read_dump(cls.text)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.written = loader.save(self.from_air, self.dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_file_layout(self) -> None:
        names = sorted(p.relative_to(self.dir).as_posix() for p in self.written)
        self.assertEqual(names, [
            "bouquets/0044-ma-qr.yaml",
            "bouquets/3622-master.yaml",
            "bouquets/6510-vtc-fullhd.yaml",
            "bouquets/6520-vtchd-basic.yaml",
            "bouquets/6550-vtc-blockedfta.yaml",
            "bouquets/6604-quang-ninh.yaml",
            "network.yaml",
            "services/ts1000.yaml",
            "services/ts3.yaml",
            "services/ts8.yaml",
        ])

    def test_bouquet_filenames_sort_by_id(self) -> None:
        """Sắp theo tên file phải cho ra đúng thứ tự id — nên thứ tự nạp tất định."""
        files = sorted((self.dir / "bouquets").glob("*.yaml"))
        ids = [int(p.name.split("-")[0], 16) for p in files]
        self.assertEqual(ids, sorted(ids))

    def test_round_trip_through_disk(self) -> None:
        self.assertEqual(loader.load(self.dir), self.from_air)

    def test_config_on_disk_still_reproduces_the_air(self) -> None:
        """Vòng dài nhất, đi qua file thật trên đĩa."""
        cfg = loader.load(self.dir)
        self.assertEqual(
            T.canon(T.write_nit(cfg.network)),
            T.canon(self.root_xml.find("NIT")),
        )
        for sdt in cfg.sdts:
            with self.subTest(ts=sdt.ts_id):
                orig = next(e for e in self.root_xml.findall("SDT")
                            if T.num(e.get("transport_stream_id")) == sdt.ts_id)
                self.assertEqual(T.canon(T.write_sdt(sdt)), T.canon(orig))
        for b in cfg.bouquets:
            with self.subTest(bouquet=hex(b.bouquet_id)):
                orig = next(e for e in self.root_xml.findall("BAT")
                            if T.num(e.get("bouquet_id")) == b.bouquet_id)
                self.assertEqual(T.canon(T.write_bat(b)), T.canon(orig))

    def test_writing_twice_gives_identical_bytes(self) -> None:
        """FR-46 ở tầng file: cùng mô hình, cùng byte trên đĩa."""
        before = {p: p.read_bytes() for p in self.written}
        loader.save(self.from_air, self.dir)
        for p, data in before.items():
            with self.subTest(file=p.name):
                self.assertEqual(p.read_bytes(), data)

    def test_vietnamese_names_stay_readable(self) -> None:
        """Không được escape thành \\uXXXX — người phải sửa được file này."""
        text = (self.dir / "services" / "ts8.yaml").read_text(encoding="utf-8")
        self.assertNotIn("\\u", text)
        self.assertIn("HA NOI 1", text)

    def test_private_data_written_as_readable_hex(self) -> None:
        text = (self.dir / "network.yaml").read_text(encoding="utf-8")
        self.assertIn("FF 04 FF 04 FF 00 FF 01 FF 30 32 35 32 FF 02", text)

    def test_services_are_not_duplicated_into_network_file(self) -> None:
        """network.yaml chỉ giữ khung; 64 dịch vụ nằm ở file riêng."""
        text = (self.dir / "network.yaml").read_text(encoding="utf-8")
        self.assertNotIn("HA NOI 1", text)
        self.assertIn("ts_id: 8", text)


class TestLoaderRefusesBadInput(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        loader.save(T.read_dump(_require()), self.dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_network_file(self) -> None:
        (self.dir / "network.yaml").unlink()
        with self.assertRaises(ConfigError):
            loader.load(self.dir)

    def test_missing_service_file(self) -> None:
        (self.dir / "services" / "ts8.yaml").unlink()
        with self.assertRaises(ConfigError):
            loader.load(self.dir)

    def test_service_file_with_wrong_ts_id_inside(self) -> None:
        """Đổi tên file mà quên sửa bên trong là lỗi im lặng — phải bắt."""
        p = self.dir / "services" / "ts8.yaml"
        p.write_text(p.read_text(encoding="utf-8").replace("ts_id: 8", "ts_id: 9", 1),
                     encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            loader.load(self.dir)
        self.assertIn("ts8.yaml", str(ctx.exception))

    def test_empty_file(self) -> None:
        (self.dir / "network.yaml").write_text("", encoding="utf-8")
        with self.assertRaises(ConfigError):
            loader.load(self.dir)


class TestSeededConfigInRepo(unittest.TestCase):
    """Bản gieo **đã commit** phải luôn khớp chuẩn vàng.

    Đọc từ HEAD chứ không đọc thư mục làm việc. Lý do đầy đủ ở ``tests/seed.py``,
    tóm tắt: ``config/`` cốt để sửa, nên một thao tác hợp lệ của người vận hành
    không được làm đỏ bộ test. Việc canh cấu hình *đang sửa* là của
    ``vtcsi preflight``, và nó phân biệt được `đổi ngầm` với `tăng thừa` —
    thứ bài test này không làm nổi.
    """

    def test_committed_config_matches_golden(self) -> None:
        td = seed.committed_config()
        try:
            cfg = loader.load(Path(td.name) / "config")
        finally:
            td.cleanup()
        air = T.read_dump(_require())
        self.assertEqual(cfg.network, air.network)
        self.assertEqual(cfg.sdts, air.sdts)
        self.assertEqual(cfg.bouquets, air.bouquets)


if __name__ == "__main__":
    unittest.main()
