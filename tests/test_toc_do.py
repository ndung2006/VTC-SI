"""Tốc độ dòng ra và nhịp lặp từng bảng — lõi, file YAML, và trang web.

Bài đáng chú ý nhất là ``TestTranChuan``: nó ghim các con số của ETSI TS 101
211 §4.1 thành thứ **chặn được**, chứ không phải một dòng chú thích mà ba
tháng sau ai đó gõ đè lên.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.config import toc_do as C
from vtcsi.model import toc_do as TD


class TestMacDinh(unittest.TestCase):
    def test_defaults_match_what_is_on_air(self) -> None:
        """Mặc định phải đúng bộ số đang phát, nếu không thì mở trang là đổi sóng."""
        t = TD.TocDo()
        self.assertEqual(t.tong, 2_000_000)
        self.assertEqual((t.bitrate_nit, t.bitrate_sdt_bat, t.bitrate_eit),
                         (20_000, 60_000, 400_000))
        self.assertEqual(t.repetition_ms(),
                         {"nit": 2000, "sdt_actual": 1000,
                          "sdt_other": 5000, "bat": 5000})
        self.assertEqual(t.eit_poll_ms, 500)

    def test_defaults_are_valid(self) -> None:
        TD.validate(TD.TocDo())

    def test_defaults_raise_no_warning(self) -> None:
        self.assertEqual(TD.canh_bao(TD.TocDo()), ())


class TestTranChuan(unittest.TestCase):
    """Trần của ETSI TS 101 211 §4.1, ghim thành thứ chặn được."""

    def test_sdt_actual_beyond_two_seconds_is_refused(self) -> None:
        with self.assertRaises(TD.TocDoError) as e:
            TD.validate(TD.TocDo(lap_sdt_actual=2_001))
        self.assertIn("101 211", str(e.exception))

    def test_exactly_at_the_limit_is_allowed(self) -> None:
        TD.validate(TD.TocDo(lap_sdt_actual=2_000))

    def test_every_table_has_its_own_ceiling(self) -> None:
        for truong, khoa in (("lap_nit", "nit"), ("lap_sdt_actual", "sdt_actual"),
                             ("lap_sdt_other", "sdt_other"), ("lap_bat", "bat")):
            with self.subTest(truong=truong):
                tran = TD.TRAN_LAP[khoa]
                TD.validate(TD.TocDo(**{truong: tran}))
                with self.assertRaises(TD.TocDoError):
                    TD.validate(TD.TocDo(**{truong: tran + 1}))

    def test_a_floor_stops_flooding_one_pid(self) -> None:
        with self.assertRaises(TD.TocDoError):
            TD.validate(TD.TocDo(lap_bat=TD.SAN_LAP_MS - 1))

    def test_zero_and_negative_are_refused(self) -> None:
        for bo in ({"bitrate_eit": 0}, {"bitrate_nit": -1}, {"tong": 0}):
            with self.subTest(bo=bo), self.assertRaises(TD.TocDoError):
                TD.validate(TD.TocDo(**bo))


class TestCanhBao(unittest.TestCase):
    """Hợp lệ nhưng đáng nghĩ lại — báo ra, không chặn."""

    def test_caps_above_the_stream_rate_are_flagged(self) -> None:
        t = TD.TocDo(tong=200_000)
        TD.validate(t)                       # hop le
        self.assertTrue(any("cùng chạm trần" in m for m in TD.canh_bao(t)))

    def test_a_cap_below_the_measured_rate_is_flagged(self) -> None:
        t = TD.TocDo(bitrate_eit=100_000)
        self.assertTrue(any("thấp hơn mức đã đo" in m for m in TD.canh_bao(t)))

    def test_the_number_format_does_not_eat_commas(self) -> None:
        """``.replace(",", ".")`` lên cả câu từng cắt câu văn làm đôi."""
        m = TD.canh_bao(TD.TocDo(bitrate_eit=100_000))[0]
        self.assertIn("100.000 bit/s,", m)

    def test_so_groups_thousands_with_dots(self) -> None:
        self.assertEqual(TD.so(2_000_000), "2.000.000")


class TestFileYaml(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_missing_file_means_defaults_not_an_error(self) -> None:
        """Hệ chưa từng mở trang này vẫn phải phát y như trước."""
        self.assertEqual(C.load(self.dir), TD.TocDo())

    def test_round_trip(self) -> None:
        C.save(TD.TocDo(lap_bat=8_000, bitrate_eit=500_000), self.dir)
        t = C.load(self.dir)
        self.assertEqual(t.lap_bat, 8_000)
        self.assertEqual(t.bitrate_eit, 500_000)

    def test_a_partial_file_fills_from_defaults(self) -> None:
        C.path_for(self.dir).write_text("lap_bat: 7000\n", encoding="utf-8")
        t = C.load(self.dir)
        self.assertEqual(t.lap_bat, 7_000)
        self.assertEqual(t.tong, TD.TocDo().tong)

    def test_an_unknown_key_is_refused(self) -> None:
        C.path_for(self.dir).write_text("lap_gi_do: 1\n", encoding="utf-8")
        with self.assertRaises(TD.TocDoError):
            C.load(self.dir)

    def test_a_non_integer_is_refused(self) -> None:
        C.path_for(self.dir).write_text("lap_bat: nhanh\n", encoding="utf-8")
        with self.assertRaises(TD.TocDoError):
            C.load(self.dir)

    def test_saving_an_illegal_value_writes_nothing(self) -> None:
        """Không bao giờ để lại một file mà chính mình không nạp lại được."""
        with self.assertRaises(TD.TocDoError):
            C.save(TD.TocDo(lap_sdt_actual=9_000), self.dir)
        self.assertFalse(C.path_for(self.dir).exists())

    def test_what_it_writes_it_can_read(self) -> None:
        C.save(TD.TocDo(), self.dir)
        self.assertEqual(C.load(self.dir), TD.TocDo())


class TestDongLenh(unittest.TestCase):
    """Bộ số phải đi được tới dòng lệnh ``tsp``, không rơi dọc đường."""

    def test_the_numbers_reach_the_command_line(self) -> None:
        from datetime import datetime, timezone

        from vtcsi.pipeline import tspbuild as B

        t = TD.TocDo(tong=1_200_000, bitrate_eit=333_000, lap_bat=7_000)
        plan = B.plan_from_config(
            build_dir="/build", eit_dir="/build/eit", ts_id=8,
            other_ts_ids=(3,), bouquet_ids=(0x6510,),
            destination="239.0.0.1:1234",
            repetition_ms=t.repetition_ms(),
            bitrates={"bitrate_nit": t.bitrate_nit,
                      "bitrate_sdt_bat": t.bitrate_sdt_bat,
                      "bitrate_eit": t.bitrate_eit,
                      "total_bitrate": t.tong,
                      "eit_poll_ms": t.eit_poll_ms},
        )
        dong = B.shell(B.build(
            plan, start_time=datetime(2026, 9, 18, tzinfo=timezone.utc)))
        self.assertIn("--bitrate 1200000", dong)
        self.assertIn("--bitrate 333000", dong)
        self.assertIn("bat-6510.xml=7000", dong)

    def test_no_table_means_the_numbers_on_air_today(self) -> None:
        """Không truyền gì thì phải ra đúng bộ số đang phát, không phải số 0."""
        from vtcsi.pipeline import tspbuild as B
        plan = B.plan_from_config(
            build_dir="/build", eit_dir="/build/eit", ts_id=8,
            other_ts_ids=(), bouquet_ids=(0x6510,),
            destination="239.0.0.1:1234")
        self.assertEqual(plan.total_bitrate, 2_000_000)
        self.assertEqual(plan.bitrate_eit, 400_000)
        self.assertEqual(plan.eit_poll_ms, 500)


class TestTrangWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        cls._seed = seed.committed_config()
        cls.goc = Path(cls._seed.name) / "config"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(self.goc, self.dir)
        from vtcsi.web.app import create_app
        self.c = TestClient(create_app(self.dir, self.root, require_login=False))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def said(self, r) -> tuple[str, str]:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or [""])[0], (q.get("err") or [""])[0]

    def post(self, **data):
        return self.c.post("/toc-do/luu", data=data, follow_redirects=False)

    def test_the_page_renders_before_the_file_exists(self) -> None:
        html = self.c.get("/toc-do").text
        self.assertIn("Nhịp lặp từng bảng", html)
        self.assertIn("chưa có file", html)

    def test_it_saves_and_reads_back(self) -> None:
        note, err = self.said(self.post(lap_bat="7000"))
        self.assertFalse(err)
        self.assertIn("dựng lại dịch vụ phát", note)
        self.assertEqual(C.load(self.dir).lap_bat, 7_000)

    def test_a_value_past_the_standard_is_refused_in_vietnamese(self) -> None:
        _, err = self.said(self.post(lap_sdt_actual="9000"))
        self.assertIn("101 211", err)
        self.assertFalse(C.path_for(self.dir).exists())

    def test_rubbish_is_refused(self) -> None:
        _, err = self.said(self.post(tong="nhanh len"))
        self.assertIn("số nguyên", err)

    def test_an_empty_box_keeps_the_current_value(self) -> None:
        C.save(TD.TocDo(lap_bat=6_000), self.dir)
        self.post(lap_bat="")
        self.assertEqual(C.load(self.dir).lap_bat, 6_000)

    def test_saving_the_same_numbers_says_so(self) -> None:
        C.save(TD.TocDo(), self.dir)
        note, _ = self.said(self.post())
        self.assertIn("không có gì thay đổi", note)

    def test_the_tab_is_reachable_from_the_other_psisi_pages(self) -> None:
        for url in ("/epg", "/dau-ra"):
            with self.subTest(url=url):
                self.assertIn("/toc-do", self.c.get(url).text)


if __name__ == "__main__":
    unittest.main()
