"""Lưới lịch một ngày — ``epg.transform.timeline``.

Lõi thuần, nên không cần file, không cần đồng hồ: ngày truyền vào. Nhờ vậy ca
khó nhất — chương trình vắt qua nửa đêm — mô tả được bằng ba dòng thay vì phải
chờ tới nửa đêm mới thử.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from vtcsi.epg.transform import timeline as T
from vtcsi.model.entities import Event

NGAY = date(2026, 9, 8)


def ev(service_id: int, gio: str, phut: int, ten: str = "x", mo: str = "") -> Event:
    """Sự kiện bắt đầu lúc ``gio`` **giờ Việt Nam**, dài ``phut`` phút."""
    h, m = (int(x) for x in gio.split(":"))
    start = datetime(NGAY.year, NGAY.month, NGAY.day, h, m, tzinfo=T.VN)
    return Event(service_id=service_id, start_utc=start.astimezone(timezone.utc),
                 duration=timedelta(minutes=phut), name=ten, encoding=0x15, text=mo)


DICH_VU = [(801, "HA NOI 1", False), (802, "ANTV", False), (855, "VOV1", True)]


class TestMinutesIntoDay(unittest.TestCase):
    def test_midnight_is_zero(self) -> None:
        self.assertEqual(T.minutes_into_day(ev(1, "00:00", 1).start_utc, NGAY), 0)

    def test_it_counts_local_time_not_utc(self) -> None:
        """Su kien 07:00 gio Viet Nam la 00:00 UTC — de nham la lech ca luoi."""
        self.assertEqual(T.minutes_into_day(ev(1, "07:00", 1).start_utc, NGAY), 420)

    def test_the_last_minute_of_the_day(self) -> None:
        self.assertEqual(T.minutes_into_day(ev(1, "23:59", 1).start_utc, NGAY), 1439)

    def test_yesterday_is_negative(self) -> None:
        e = ev(1, "23:00", 60)
        self.assertEqual(T.minutes_into_day(e.start_utc, date(2026, 9, 9)), -60)

    def test_local_day_of_a_utc_moment(self) -> None:
        """22:00 UTC ngay 07/09 la 05:00 ngay 08/09 gio Viet Nam."""
        moment = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)
        self.assertEqual(T.local_day(moment), NGAY)


class TestTouches(unittest.TestCase):
    def test_an_event_inside_the_day(self) -> None:
        self.assertTrue(T.touches(ev(1, "10:00", 30), NGAY))

    def test_an_event_on_another_day(self) -> None:
        self.assertFalse(T.touches(ev(1, "10:00", 30), date(2026, 9, 10)))

    def test_an_event_crossing_midnight_belongs_to_both_days(self) -> None:
        """Bo no khoi ngay sau se tao mot lo hong khong co that luc nua dem."""
        e = ev(1, "23:30", 60)
        self.assertTrue(T.touches(e, NGAY))
        self.assertTrue(T.touches(e, date(2026, 9, 9)))

    def test_an_event_ending_exactly_at_midnight_is_not_the_next_day(self) -> None:
        e = ev(1, "23:30", 30)
        self.assertTrue(T.touches(e, NGAY))
        self.assertFalse(T.touches(e, date(2026, 9, 9)))


class TestGaps(unittest.TestCase):
    def one(self, *cap):
        return T.find_gaps(tuple(T.Slot(start=a, minutes=b - a, title="x")
                                 for a, b in cap))

    def test_back_to_back_has_no_gap(self) -> None:
        self.assertEqual(self.one((0, 60), (60, 120)), ())

    def test_a_real_gap_is_found(self) -> None:
        self.assertEqual(self.one((0, 60), (90, 120)), ((60, 30),))

    def test_a_tiny_gap_is_ignored(self) -> None:
        """Chenh mot hai phut la chuyen thuong cua bien tap."""
        self.assertEqual(self.one((0, 60), (62, 120)), ())

    def test_the_threshold_is_inclusive(self) -> None:
        self.assertEqual(self.one((0, 60), (60 + T.MIN_GAP, 120)),
                         ((60, T.MIN_GAP),))

    def test_nothing_before_the_first_or_after_the_last(self) -> None:
        """Kenh len song tu 05:00 khong co 'lo hong nam tieng'."""
        self.assertEqual(self.one((300, 360)), ())

    def test_overlapping_events_do_not_invent_a_gap(self) -> None:
        """Lich that co chuong trinh long nhau; so voi o lien truoc se bao bua."""
        self.assertEqual(self.one((0, 180), (30, 60), (180, 240)), ())

    def test_a_gap_after_a_long_overlapping_block(self) -> None:
        self.assertEqual(self.one((0, 180), (30, 60), (240, 300)), ((180, 60),))

    def test_no_events_no_gaps(self) -> None:
        self.assertEqual(T.find_gaps(()), ())


class TestBuild(unittest.TestCase):
    def test_every_listed_service_gets_a_row(self) -> None:
        b = T.build((ev(801, "10:00", 30),), DICH_VU, NGAY)
        self.assertEqual([r.service_id for r in b.rows], [801, 802, 855])

    def test_a_service_with_no_events_is_still_a_row(self) -> None:
        """Chinh nhung dong rong moi la thu dang nhin."""
        b = T.build((ev(801, "10:00", 30),), DICH_VU, NGAY)
        self.assertTrue(b.rows[1].empty)
        self.assertEqual(b.empty, 2)
        self.assertEqual(b.with_schedule, 1)

    def test_events_of_a_service_not_listed_are_dropped(self) -> None:
        """Day la cho yeu cau 'tat EPG thi khong hien' thanh su that."""
        b = T.build((ev(999, "10:00", 30), ev(801, "11:00", 30)), DICH_VU, NGAY)
        self.assertEqual(b.events, 1)
        self.assertNotIn(999, [r.service_id for r in b.rows])

    def test_slots_come_out_in_time_order(self) -> None:
        b = T.build((ev(801, "20:00", 30), ev(801, "06:00", 30),
                     ev(801, "13:00", 30)), DICH_VU, NGAY)
        self.assertEqual([s.start for s in b.rows[0].slots], [360, 780, 1200])

    def test_the_title_and_text_survive(self) -> None:
        b = T.build((ev(801, "10:00", 30, "Thời sự", "Bản tin trưa"),),
                    DICH_VU, NGAY)
        s = b.rows[0].slots[0]
        self.assertEqual(s.title, "Thời sự")
        self.assertEqual(s.text, "Bản tin trưa")

    def test_a_zero_length_event_still_gets_a_minute(self) -> None:
        """Mot o rong 0 px thi khong bam duoc, va nguoi ta se tuong no bien mat."""
        b = T.build((ev(801, "10:00", 0),), DICH_VU, NGAY)
        self.assertEqual(b.rows[0].slots[0].minutes, 1)

    def test_an_event_from_yesterday_starts_before_zero(self) -> None:
        b = T.build((ev(801, "23:30", 60),), DICH_VU, date(2026, 9, 9))
        self.assertEqual(b.rows[0].slots[0].start, -30)
        self.assertEqual(b.rows[0].slots[0].end, 30)

    def test_other_days_are_left_out(self) -> None:
        b = T.build((ev(801, "10:00", 30),), DICH_VU, date(2026, 9, 20))
        self.assertEqual(b.events, 0)

    def test_the_radio_flag_reaches_the_row(self) -> None:
        b = T.build((), DICH_VU, NGAY)
        self.assertEqual([r.radio for r in b.rows], [False, False, True])

    def test_the_summary_adds_up(self) -> None:
        b = T.build((ev(801, "06:00", 60), ev(801, "12:00", 60),
                     ev(802, "08:00", 30)), DICH_VU, NGAY)
        self.assertEqual(b.events, 3)
        self.assertEqual(b.with_schedule, 2)
        self.assertEqual(b.empty, 1)
        self.assertEqual(b.gaps, 1)      # 07:00 → 12:00 tren kenh 801

    def test_an_empty_service_list_gives_an_empty_board(self) -> None:
        b = T.build((ev(801, "10:00", 30),), [], NGAY)
        self.assertEqual(b.rows, ())
        self.assertEqual(b.events, 0)


if __name__ == "__main__":
    unittest.main()


class TestTheEpgSwitch(unittest.TestCase):
    """Kenh tat EPG: van co dong, nhung dong rong.

    Luat nam o day chu khong o noi goi. Neu noi goi phai nho loc thi som muon
    se co mot noi goi quen, va cong tac tren giao dien thanh loi hua suong.
    """

    TAT = [(801, "HA NOI 1", False, False), (802, "ANTV", False, True)]

    def test_the_row_is_still_there(self) -> None:
        b = T.build((), self.TAT, NGAY)
        self.assertEqual([r.service_id for r in b.rows], [801, 802])

    def test_the_row_is_marked(self) -> None:
        b = T.build((), self.TAT, NGAY)
        self.assertEqual([r.epg for r in b.rows], [False, True])

    def test_its_events_are_dropped_here_not_upstream(self) -> None:
        b = T.build((ev(801, "10:00", 30), ev(802, "10:00", 30)), self.TAT, NGAY)
        self.assertEqual(b.rows[0].slots, ())
        self.assertEqual(len(b.rows[1].slots), 1)

    def test_a_turned_off_row_never_shows_gaps(self) -> None:
        b = T.build((ev(801, "06:00", 30), ev(801, "20:00", 30)), self.TAT, NGAY)
        self.assertEqual(b.rows[0].gaps, ())

    def test_off_is_counted_apart_from_missing(self) -> None:
        """`empty` la su co; `off` la lua chon. Gop lai thi mat het y nghia."""
        b = T.build((ev(801, "10:00", 30),), self.TAT, NGAY)
        self.assertEqual(b.off, 1)
        self.assertEqual(b.empty, 1)          # 802 bat ma khong co lich
        self.assertEqual(b.with_schedule, 0)
        self.assertEqual(b.events, 0)

    def test_the_three_counters_cover_every_row(self) -> None:
        b = T.build((ev(802, "10:00", 30),), self.TAT, NGAY)
        self.assertEqual(len(b.rows), b.with_schedule + b.empty + b.off)

    def test_a_three_tuple_still_means_on(self) -> None:
        """Noi goi nao khong quan tam toi cong tac van viet y nhu cu."""
        b = T.build((ev(801, "10:00", 30),), DICH_VU, NGAY)
        self.assertTrue(all(r.epg for r in b.rows))
        self.assertEqual(b.off, 0)
        self.assertEqual(b.events, 1)
