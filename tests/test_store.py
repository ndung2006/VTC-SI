"""Kho lịch trên đĩa — thư mục file chính là trạng thái.

Không có cơ sở dữ liệu, không có file trạng thái ẩn. Hệ quả kiểm được: khởi
động lại không mất gì, và thêm một file ngày là đủ để cửa sổ dài ra.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vtcsi.epg import store
from vtcsi.epg.transform import window as W

SAMPLE = Path(__file__).parent / "data" / "epg-sample.xml"
REAL = Path(__file__).parent.parent / "Bang mau" / "File xml đầu vào cho EPG.xml"

UTC = timezone.utc
DAY0 = datetime(2026, 9, 7, 17, 0, tzinfo=UTC)   # 2026-09-08 00:00 gio Ha Noi


def _day_file(src: Path, dst: Path, shift_days: int) -> None:
    """Tạo file 'ngày hôm sau' bằng cách dời mọi mốc thời gian."""
    text = src.read_text(encoding="utf-8")
    for d in range(20, 0, -1):
        old = "2026-09-%02d" % d
        new = "2026-09-%02d" % (d + shift_days)
        text = text.replace(old, new)
    dst.write_text(text, encoding="utf-8")


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class TestThuTuNhan(StoreCase):
    """Thứ tự nạp phải là thứ tự **nhận**, không phải thứ tự **tên**.

    Dựng lại đúng tình huống trên máy phát ngày 2026-09-15: file tên
    ``2026-09-15.xml`` là đợt CŨ (nhận 08:29), file tên ``2026-09-14.xml`` là
    đợt MỚI (nhận 09:37). Sắp theo tên thì đợt cũ thắng — ngược hoàn toàn.
    """

    def _dat(self, ten: str, shift_days: int, mtime: float) -> Path:
        p = self.inbox / ten
        _day_file(SAMPLE, p, shift_days)
        os.utime(p, (mtime, mtime))
        return p

    def test_newest_file_is_loaded_last_even_if_its_name_sorts_first(self) -> None:
        self._dat("2026-09-15.xml", 0, 1_000_000)   # ten dung sau, nhan TRUOC
        self._dat("2026-09-14.xml", 1, 2_000_000)   # ten dung truoc, nhan SAU
        thu_tu = [x.path.name for x in store.load_all(self.inbox)]
        self.assertEqual(thu_tu, ["2026-09-15.xml", "2026-09-14.xml"])

    def test_same_mtime_falls_back_to_name_so_it_stays_deterministic(self) -> None:
        self._dat("b.xml", 0, 1_500_000)
        self._dat("a.xml", 1, 1_500_000)
        thu_tu = [x.path.name for x in store.load_all(self.inbox)]
        self.assertEqual(thu_tu, ["a.xml", "b.xml"])

    def test_coverage_reaches_the_window(self) -> None:
        """Phạm vi tự khai phải đi hết từ file tới hàm gộp, không rơi dọc đường."""
        self._dat("2026-09-15.xml", 0, 1_000_000)
        nap = store.load_all(self.inbox)
        self.assertTrue(nap[0].coverage)


class TestEmptyAndBroken(StoreCase):
    def test_missing_directory(self) -> None:
        with self.assertRaises(store.StoreError):
            store.load_all(self.inbox / "khong-co")

    def test_empty_directory(self) -> None:
        with self.assertRaises(store.StoreError) as ctx:
            store.load_all(self.inbox)
        self.assertIn("rong", str(ctx.exception))

    def test_refuses_mixed_transport_streams(self) -> None:
        """Mỗi TS một hộp thư — trộn vào là lỗi cấu hình, không phải dữ liệu."""
        shutil.copy(SAMPLE, self.inbox / "a.xml")
        other = SAMPLE.read_text(encoding="utf-8").replace(
            'TRANSPORT_STREAM id="8"', 'TRANSPORT_STREAM id="9"')
        (self.inbox / "b.xml").write_text(other, encoding="utf-8")
        with self.assertRaises(store.StoreError) as ctx:
            store.build(self.inbox, DAY0)
        self.assertIn("nhieu transport stream", str(ctx.exception))


class TestBuild(StoreCase):
    def setUp(self) -> None:
        super().setUp()
        shutil.copy(SAMPLE, self.inbox / "2026-09-08.xml")

    def test_single_day(self) -> None:
        r = store.build(self.inbox, DAY0)
        self.assertEqual(r.ts_id, 8)
        self.assertEqual(r.original_network_id, 12901)
        self.assertEqual(len(r.files), 1)
        self.assertEqual(r.services, (801, 802))
        self.assertTrue(all(e.event_id is not None for e in r.events))

    def test_adding_a_day_lengthens_the_window(self) -> None:
        before = len(store.build(self.inbox, DAY0).events)
        _day_file(SAMPLE, self.inbox / "2026-09-09.xml", 1)
        after = store.build(self.inbox, DAY0).events
        self.assertEqual(len(after), before * 2)
        self.assertEqual(len(after), len({(e.service_id, e.event_id) for e in after}),
                         "event_id phai duy nhat trong ca cua so")

    def test_reading_twice_gives_the_same_result(self) -> None:
        """Trạng thái nằm trong file, nên đọc lại là đủ — không cần khôi phục gì."""
        a = store.build(self.inbox, DAY0)
        b = store.build(self.inbox, DAY0)
        self.assertEqual(a.events, b.events)

    def test_reloading_the_same_day_is_idempotent(self) -> None:
        """Nạp lại cùng nội dung dưới tên khác không nhân đôi sự kiện."""
        before = store.build(self.inbox, DAY0).events
        shutil.copy(SAMPLE, self.inbox / "2026-09-08-nap-lai.xml")
        self.assertEqual(store.build(self.inbox, DAY0).events, before)

    def test_window_moves_forward(self) -> None:
        _day_file(SAMPLE, self.inbox / "2026-09-09.xml", 1)
        later = DAY0 + timedelta(days=1)
        out = store.build(self.inbox, later).events
        self.assertTrue(all(e.end_utc > later for e in out))

    def test_depth_limit_respected(self) -> None:
        for d in range(1, 4):
            _day_file(SAMPLE, self.inbox / f"2026-09-{8 + d:02d}.xml", d)
        shallow = store.build(self.inbox, DAY0, depth_hours=24).events
        deep = store.build(self.inbox, DAY0, depth_hours=192).events
        self.assertLess(len(shallow), len(deep))


class TestRejectedEventsAreReported(StoreCase):
    def test_overlong_event_is_separated_not_fatal(self) -> None:
        """RO-22: một sự kiện hỏng không được làm sập cả mẻ."""
        text = SAMPLE.read_text(encoding="utf-8").replace(
            'duration="PT00H10M00S"', 'duration="PT48H00M01S"', 1)
        (self.inbox / "co-loi.xml").write_text(text, encoding="utf-8")
        r = store.build(self.inbox, DAY0)
        self.assertEqual(len(r.rejected), 1)
        self.assertEqual(r.rejected[0].duration, timedelta(hours=48, seconds=1))
        self.assertTrue(r.events, "phan con lai van phai dung duoc")


class TestStaleFiles(StoreCase):
    def test_finds_files_entirely_in_the_past(self) -> None:
        shutil.copy(SAMPLE, self.inbox / "2026-09-08.xml")
        _day_file(SAMPLE, self.inbox / "2026-09-12.xml", 4)
        stale = store.stale_files(self.inbox, DAY0 + timedelta(days=3))
        self.assertEqual([p.name for p in stale], ["2026-09-08.xml"])

    def test_nothing_stale_yet(self) -> None:
        shutil.copy(SAMPLE, self.inbox / "2026-09-08.xml")
        self.assertEqual(store.stale_files(self.inbox, DAY0), [])

    def test_does_not_delete_anything(self) -> None:
        """Chỉ báo, không xoá — quyết định là của người hoặc việc định kỳ."""
        shutil.copy(SAMPLE, self.inbox / "2026-09-08.xml")
        store.stale_files(self.inbox, DAY0 + timedelta(days=30))
        self.assertTrue((self.inbox / "2026-09-08.xml").exists())


class TestAgainstRealFile(StoreCase):
    def setUp(self) -> None:
        super().setUp()
        if not REAL.exists():
            raise unittest.SkipTest("khong tim thay file lich that")
        shutil.copy(REAL, self.inbox / "2026-09-08.xml")

    def test_consumes_every_service_in_the_file(self) -> None:
        """FR-53: 44 dịch vụ, không phải 18 như Barrowa đang gán nguồn."""
        r = store.build(self.inbox, DAY0)
        self.assertEqual(len(r.services), 44)
        self.assertEqual(len(r.events), 2365)

    def test_alarm_fires_on_one_day_of_data(self) -> None:
        r = store.build(self.inbox, DAY0)
        thin = W.services_below(r.events, DAY0, hours=120)
        self.assertEqual(len(thin), 44, "mot ngay du lieu thi ca 44 deu mong")


if __name__ == "__main__":
    unittest.main()
