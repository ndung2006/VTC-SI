"""Cửa sổ 192 giờ — gộp file theo ngày, cắt, khử chồng lấn.

Bài quan trọng nhất là ``test_eight_daily_files_fill_the_window``: nó dựng
đúng tình huống RO-13 — nguồn chỉ phát hành một ngày mỗi file — và chứng minh
tám file liên tiếp ghép lại đủ độ sâu EIT schedule cần.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vtcsi.epg.transform import eventid as EID
from vtcsi.epg.transform import parse as P
from vtcsi.epg.transform import window as W
from vtcsi.model.entities import Event

SAMPLE = Path(__file__).parent / "data" / "epg-sample.xml"
REAL = Path(__file__).parent.parent / "Bang mau" / "File xml đầu vào cho EPG.xml"

UTC = timezone.utc
T0 = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)


def ev(service_id: int, start: datetime, minutes: int, name: str = "x") -> Event:
    return Event(
        service_id=service_id,
        start_utc=start,
        duration=timedelta(minutes=minutes),
        name=name,
        encoding=0x15,
    )


def shift(events, days: int):
    d = timedelta(days=days)
    return tuple(
        Event(
            service_id=e.service_id, start_utc=e.start_utc + d, duration=e.duration,
            name=e.name, encoding=e.encoding, free_ca_mode=e.free_ca_mode,
            running_status=e.running_status, text=e.text,
            source_event_id=e.source_event_id,
        )
        for e in events
    )


class TestMerge(unittest.TestCase):
    def test_later_batch_wins_on_same_key(self) -> None:
        old = (ev(801, T0, 30, "ten cu"),)
        new = (ev(801, T0, 30, "ten moi"),)
        out = W.merge(old, new)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].name, "ten moi")

    def test_different_start_is_a_different_event(self) -> None:
        a = (ev(801, T0, 30),)
        b = (ev(801, T0 + timedelta(minutes=30), 30),)
        self.assertEqual(len(W.merge(a, b)), 2)

    def test_same_start_different_service_kept_apart(self) -> None:
        self.assertEqual(len(W.merge((ev(801, T0, 30),), (ev(802, T0, 30),))), 2)

    def test_output_order_is_deterministic(self) -> None:
        a = (ev(802, T0, 30), ev(801, T0, 30))
        b = (ev(801, T0, 30), ev(802, T0, 30))
        self.assertEqual(W.merge(a), W.merge(b))


class TestClip(unittest.TestCase):
    def test_keeps_event_in_progress(self) -> None:
        """Sự kiện đang phát dở vẫn cần cho p/f, không được cắt."""
        running = ev(801, T0 - timedelta(minutes=10), 30)
        self.assertEqual(W.clip((running,), T0), (running,))

    def test_drops_event_already_finished(self) -> None:
        past = ev(801, T0 - timedelta(hours=2), 30)
        self.assertEqual(W.clip((past,), T0), ())

    def test_drops_event_beyond_the_window(self) -> None:
        far = ev(801, T0 + timedelta(hours=200), 30)
        self.assertEqual(W.clip((far,), T0), ())
        self.assertEqual(len(W.clip((far,), T0, depth_hours=240)), 1)

    def test_naive_now_refused(self) -> None:
        with self.assertRaises(ValueError):
            W.clip((), datetime(2026, 9, 8))


class TestDropOverlaps(unittest.TestCase):
    def test_no_overlap_is_untouched(self) -> None:
        a = ev(801, T0, 30)
        b = ev(801, T0 + timedelta(minutes=30), 30)
        self.assertEqual(W.drop_overlaps((a, b)), (a, b))

    def test_later_event_that_overlaps_is_dropped(self) -> None:
        a = ev(801, T0, 60, "giu")
        b = ev(801, T0 + timedelta(minutes=30), 60, "bo")
        out = W.drop_overlaps((a, b))
        self.assertEqual([e.name for e in out], ["giu"])

    def test_overlap_across_services_is_fine(self) -> None:
        a = ev(801, T0, 60)
        b = ev(802, T0, 60)
        self.assertEqual(len(W.drop_overlaps((a, b))), 2)

    def test_touching_events_do_not_count_as_overlap(self) -> None:
        a = ev(801, T0, 30)
        b = ev(801, T0 + timedelta(minutes=30), 30)
        self.assertEqual(len(W.drop_overlaps((a, b))), 2)


class TestDepth(unittest.TestCase):
    def test_depth_measured_to_end_not_start(self) -> None:
        long_one = ev(801, T0 + timedelta(hours=10), 120)
        d = W.depth_by_service((long_one,), T0)
        self.assertEqual(d[801], timedelta(hours=12))

    def test_services_below_threshold(self) -> None:
        events = (
            ev(801, T0 + timedelta(hours=1), 60),      # sau 2 gio
            ev(802, T0 + timedelta(hours=150), 60),    # sau 151 gio
        )
        self.assertEqual(W.services_below(events, T0, hours=120), (801,))


class TestEightDailyFiles(unittest.TestCase):
    """RO-13: nguồn chỉ phát hành một ngày mỗi file."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.day0 = P.parse(SAMPLE.read_text(encoding="utf-8")).events
        cls.start = min(e.start_utc for e in cls.day0)

    def test_eight_daily_files_fill_the_window(self) -> None:
        batches = [shift(self.day0, d) for d in range(8)]
        out = W.build(batches, self.start)
        self.assertEqual(len(out), len(self.day0) * 8)
        span = max(e.end_utc for e in out) - self.start
        self.assertGreater(span, timedelta(days=7))

    def test_window_plus_event_ids_survive_together(self) -> None:
        """Hai mảnh ghép lại: cửa sổ 8 ngày và id tất định, không va chạm."""
        batches = [shift(self.day0, d) for d in range(8)]
        assigned = EID.assign_all(W.build(batches, self.start))
        pairs = [(e.service_id, e.event_id) for e in assigned]
        self.assertEqual(len(set(pairs)), len(pairs))

    def test_reloading_the_same_day_changes_nothing(self) -> None:
        once = W.build([shift(self.day0, d) for d in range(8)], self.start)
        twice = W.build(
            [shift(self.day0, d) for d in range(8)] + [shift(self.day0, 3)], self.start
        )
        self.assertEqual(once, twice)

    def test_rolling_forward_drops_the_oldest_day(self) -> None:
        batches = [shift(self.day0, d) for d in range(8)]
        later = self.start + timedelta(days=2)
        out = W.build(batches, later)
        self.assertTrue(all(e.end_utc > later for e in out))
        self.assertLess(len(out), len(self.day0) * 8)


class TestAgainstRealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not REAL.exists():
            raise unittest.SkipTest("khong tim thay file lich that")
        cls.events = P.parse(REAL.read_text(encoding="utf-8")).events
        cls.start = min(e.start_utc for e in cls.events)

    def test_one_real_day_gives_one_day_of_depth(self) -> None:
        out = W.build([self.events], self.start)
        self.assertEqual(len(out), len(self.events), "du lieu that khong co chong lan")
        depths = W.depth_by_service(out, self.start)
        self.assertEqual(len(depths), 44)
        self.assertLess(max(depths.values()), timedelta(hours=25))

    def test_all_44_services_are_below_the_120h_alarm(self) -> None:
        """Với một file một ngày, cả 44 dịch vụ đều dưới ngưỡng cảnh báo."""
        out = W.build([self.events], self.start)
        self.assertEqual(len(W.services_below(out, self.start, hours=120)), 44)



class TestOnlyServices(unittest.TestCase):
    """Lọc theo công tắc EPG của từng kênh.

    Cờ ``EIT_schedule_flag`` trong SDT chỉ là *lời khai* — đầu thu vẫn hiện EPG
    nếu bảng có trên sóng. Nên tắt EPG một kênh **thật sự** là không sinh bảng
    cho nó, và đó là việc của hàm này.
    """

    def setUp(self) -> None:
        self.events = (
            ev(1, T0, 60),
            ev(2, T0, 60),
            ev(3, T0, 60),
            ev(1, T0 + timedelta(hours=1), 60),
        )

    def test_it_keeps_only_what_is_allowed(self) -> None:
        keep, _ = W.only_services(self.events, {1, 3})
        self.assertEqual({e.service_id for e in keep}, {1, 3})
        self.assertEqual(len(keep), 3)

    def test_it_names_what_it_dropped(self) -> None:
        """Tat EPG mot kenh phai NOI RA — ba thang sau con nguoi ta hoi lai."""
        _, bo = W.only_services(self.events, {1})
        self.assertEqual(bo, (2, 3))

    def test_allowing_everything_drops_nothing(self) -> None:
        keep, bo = W.only_services(self.events, {1, 2, 3})
        self.assertEqual(keep, self.events)
        self.assertEqual(bo, ())

    def test_allowing_nothing_keeps_nothing(self) -> None:
        keep, bo = W.only_services(self.events, set())
        self.assertEqual(keep, ())
        self.assertEqual(bo, (1, 2, 3))

    def test_a_service_with_no_events_is_not_reported_as_dropped(self) -> None:
        """Kenh khong co su kien thi khong co gi de bo — keu la keu bua."""
        _, bo = W.only_services(self.events, {1, 2, 3, 99})
        self.assertEqual(bo, ())

    def test_order_is_untouched(self) -> None:
        keep, _ = W.only_services(self.events, {1, 2, 3})
        self.assertEqual([e.start_utc for e in keep],
                         [e.start_utc for e in self.events])


if __name__ == "__main__":
    unittest.main()
