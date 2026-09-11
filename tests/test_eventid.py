"""AC-14 — cấp ``event_id`` tất định, không trùng trong cửa sổ 8 ngày.

Bài quan trọng nhất ở đây là ``test_eight_days_no_collision``: nó dựng đúng
kịch bản mà RO-12 cảnh báo — tám ngày lịch cùng nằm trong EIT schedule — và
chứng minh cách cấp id mới chịu được, trong khi id của nguồn thì không.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vtcsi.epg.transform import eventid as EID
from vtcsi.epg.transform import parse as P
from vtcsi.model.entities import Event

SAMPLE = Path(__file__).parent / "data" / "epg-sample.xml"
REAL = Path(__file__).parent.parent / "Bang mau" / "File xml đầu vào cho EPG.xml"


def _shift(events: tuple[Event, ...], days: int) -> list[Event]:
    """Dời cả tập sang ``days`` ngày — giả lập file lịch của ngày khác."""
    d = timedelta(days=days)
    return [
        Event(
            service_id=e.service_id,
            start_utc=e.start_utc + d,
            duration=e.duration,
            name=e.name,
            encoding=e.encoding,
            free_ca_mode=e.free_ca_mode,
            running_status=e.running_status,
            text=e.text,
            source_event_id=e.source_event_id,
        )
        for e in events
    ]


class TestFormula(unittest.TestCase):
    def test_epoch_is_zero(self) -> None:
        self.assertEqual(EID.event_id_for(EID.EPOCH), 0)

    def test_one_minute_steps_by_one(self) -> None:
        self.assertEqual(EID.event_id_for(EID.EPOCH + timedelta(minutes=1)), 1)
        self.assertEqual(EID.event_id_for(EID.EPOCH + timedelta(minutes=1234)), 1234)

    def test_wraps_at_65536_minutes(self) -> None:
        self.assertEqual(EID.event_id_for(EID.EPOCH + timedelta(minutes=EID.MODULUS)), 0)
        self.assertAlmostEqual(EID.WRAP_DAYS, 45.51, places=2)

    def test_wrap_period_comfortably_exceeds_the_schedule_window(self) -> None:
        """192 giờ = 8 ngày. Chu kỳ quay vòng phải lớn hơn nhiều."""
        self.assertGreater(EID.WRAP_DAYS, 8 * 4)

    def test_same_instant_in_another_timezone_gives_same_id(self) -> None:
        utc = datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)
        hanoi = datetime(2026, 9, 8, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        self.assertEqual(EID.event_id_for(utc), EID.event_id_for(hanoi))

    def test_naive_datetime_refused(self) -> None:
        with self.assertRaises(ValueError):
            EID.event_id_for(datetime(2026, 9, 8, 0, 0))

    def test_before_epoch_refused(self) -> None:
        with self.assertRaises(ValueError):
            EID.event_id_for(EID.EPOCH - timedelta(minutes=1))


class TestAssignAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.events = P.parse(SAMPLE.read_text(encoding="utf-8")).events

    def test_every_event_gets_an_id_in_range(self) -> None:
        for e in EID.assign_all(self.events):
            self.assertIsNotNone(e.event_id)
            self.assertTrue(0 <= e.event_id < 65536)

    def test_reload_is_stable(self) -> None:
        """Nạp lại cùng dữ liệu không được đổi id — nếu không đầu thu thấy
        toàn sự kiện 'mới' mỗi lần ta nạp file."""
        a = [e.event_id for e in EID.assign_all(self.events)]
        b = [e.event_id for e in EID.assign_all(P.parse(SAMPLE.read_text(encoding="utf-8")).events)]
        self.assertEqual(a, b)

    def test_input_order_does_not_matter(self) -> None:
        forward = {(e.service_id, e.event_id) for e in EID.assign_all(self.events)}
        backward = {(e.service_id, e.event_id) for e in EID.assign_all(list(reversed(self.events)))}
        self.assertEqual(forward, backward)

    def test_collision_is_raised_not_swallowed(self) -> None:
        e = self.events[0]
        clone = Event(
            service_id=e.service_id,
            start_utc=e.start_utc + timedelta(seconds=30),  # cung phut
            duration=e.duration,
            name="khac ten, cung phut",
            encoding=e.encoding,
        )
        with self.assertRaises(EID.EventIdCollision):
            EID.assign_all([e, clone])

    def test_same_minute_different_service_is_fine(self) -> None:
        """event_id chi can duy nhat trong pham vi mot dich vu."""
        e = self.events[0]
        other = Event(
            service_id=e.service_id + 1,
            start_utc=e.start_utc,
            duration=e.duration,
            name="dich vu khac",
            encoding=e.encoding,
        )
        out = EID.assign_all([e, other])
        self.assertEqual(out[0].event_id, out[1].event_id)


class TestEightDayWindow(unittest.TestCase):
    """Đúng kịch bản RO-12 cảnh báo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.day0 = P.parse(SAMPLE.read_text(encoding="utf-8")).events

    def test_source_ids_would_collide(self) -> None:
        """Chứng minh vấn đề có thật trước khi chứng minh cách chữa."""
        pairs = [
            (e.service_id, e.source_event_id)
            for d in range(8)
            for e in _shift(self.day0, d)
        ]
        self.assertLess(len(set(pairs)), len(pairs), "id cua nguon dang le phai trung")

    def test_eight_days_no_collision(self) -> None:
        window = [e for d in range(8) for e in _shift(self.day0, d)]
        assigned = EID.assign_all(window)
        pairs = [(e.service_id, e.event_id) for e in assigned]
        self.assertEqual(len(set(pairs)), len(pairs))
        self.assertEqual(len(assigned), len(self.day0) * 8)


class TestAgainstRealFile(unittest.TestCase):
    """Chạy trên toàn bộ file thật nếu nó có mặt — 44 dịch vụ, 2 365 sự kiện."""

    @classmethod
    def setUpClass(cls) -> None:
        if not REAL.exists():
            raise unittest.SkipTest("khong tim thay file lich that")
        cls.sched = P.parse(REAL.read_text(encoding="utf-8"))

    def test_shape_matches_survey(self) -> None:
        services = {e.service_id for e in self.sched.events}
        self.assertEqual(len(services), 44)
        self.assertEqual(min(services), 801)
        self.assertEqual(max(services), 844)
        self.assertEqual(len(self.sched.events), 2365)

    def test_eight_days_of_the_real_file_no_collision(self) -> None:
        window = [e for d in range(8) for e in _shift(self.sched.events, d)]
        assigned = EID.assign_all(window)
        pairs = {(e.service_id, e.event_id) for e in assigned}
        self.assertEqual(len(pairs), len(window))


if __name__ == "__main__":
    unittest.main()
