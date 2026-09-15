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
from vtcsi.model.entities import Coverage, Event

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

    def test_a_rescheduled_programme_leaves_the_old_one_behind(self) -> None:
        """Không có phạm vi thì dời giờ để lại rác — lỗi đã lên sóng thật."""
        cu = (ev(801, T0, 60, "ban cu"),)
        moi = (ev(801, T0 + timedelta(minutes=30), 60, "ban moi"),)
        out = W.merge(cu, moi)
        self.assertEqual(len(out), 2)
        # Và `drop_overlaps` sau đó giữ đúng bản CŨ, vứt bản mới.
        con_lai = W.drop_overlaps(out)
        self.assertEqual([e.name for e in con_lai], ["ban cu"])

    def test_same_start_different_service_kept_apart(self) -> None:
        self.assertEqual(len(W.merge((ev(801, T0, 30),), (ev(802, T0, 30),))), 2)

    def test_output_order_is_deterministic(self) -> None:
        a = (ev(802, T0, 30), ev(801, T0, 30))
        b = (ev(801, T0, 30), ev(802, T0, 30))
        self.assertEqual(W.merge(a), W.merge(b))


def phu(service_id: int, dau: datetime, gio: int) -> Coverage:
    return Coverage(service_id=service_id, start_utc=dau,
                    end_utc=dau + timedelta(hours=gio))


class TestMergeTheoPhamVi(unittest.TestCase):
    """Đợt giao khai phạm vi thì nó **thay trọn** khoảng đó."""

    def test_rescheduled_programme_replaces_instead_of_duplicating(self) -> None:
        cu = (ev(801, T0, 60, "ban cu"),)
        moi = ((ev(801, T0 + timedelta(minutes=30), 60, "ban moi"),),
               (phu(801, T0, 24),))
        out = W.merge(cu, moi)
        self.assertEqual([e.name for e in out], ["ban moi"])

    def test_a_cancelled_programme_disappears(self) -> None:
        """Đợt mới phủ khoảng đó mà không nhắc tới nó nữa: nó phải biến mất."""
        cu = (ev(801, T0, 60, "da huy"),)
        out = W.merge(cu, ((), (phu(801, T0, 24),)))
        self.assertEqual(out, ())

    def test_it_only_touches_the_declared_service(self) -> None:
        cu = (ev(801, T0, 60), ev(802, T0, 60))
        out = W.merge(cu, ((), (phu(801, T0, 24),)))
        self.assertEqual([e.service_id for e in out], [802])

    def test_events_outside_the_declared_window_survive(self) -> None:
        """Đợt mới phụ trách hôm nay thì không được đụng tới ngày mai."""
        cu = (ev(801, T0, 60, "hom nay"),
              ev(801, T0 + timedelta(days=3), 60, "ngay kia"))
        out = W.merge(cu, ((), (phu(801, T0, 24),)))
        self.assertEqual([e.name for e in out], ["ngay kia"])

    def test_batch_without_coverage_deletes_nothing(self) -> None:
        """Không khai phạm vi thì không được quyền xoá — file lỗi không quét sạch ngày."""
        cu = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(8))
        out = W.merge(cu, (ev(801, T0 + timedelta(hours=20), 60),))
        self.assertEqual(len(out), 9)

    def test_declared_window_is_inclusive_at_both_ends(self) -> None:
        cu = (ev(801, T0, 10), ev(801, T0 + timedelta(hours=24), 10))
        out = W.merge(cu, ((), (phu(801, T0, 24),)))
        self.assertEqual(out, ())

    def test_real_file_declares_coverage(self) -> None:
        sched = P.parse(SAMPLE.read_text(encoding="utf-8"))
        self.assertTrue(sched.coverage, "file mau phai khai start_time/end_time")
        for c in sched.coverage:
            self.assertLess(c.start_utc, c.end_utc)
            self.assertTrue(any(c.chua(e) for e in sched.events),
                            f"pham vi cua {c.service_id} khong chua su kien nao")


class TestDoiSoDichVu(unittest.TestCase):
    """``epg_source_id`` — lịch đến dưới một số, lên sóng dưới số khác.

    Thật trên hệ: Quảng Trị lên sóng là 825, trong file lịch là 875. Không đổi
    số thì ``only_services`` loại sạch và kênh **không có EPG nào**.
    """

    def test_it_renames_the_service(self) -> None:
        out = W.remap(((ev(875, T0, 30),), ()), {875: 825})
        self.assertEqual([e.service_id for e in out[0]], [825])

    def test_it_renames_the_declared_coverage_too(self) -> None:
        """Bỏ sót phạm vi thì đợt mới không thay được đợt cũ của chính kênh đó."""
        out = W.remap(((), (phu(875, T0, 24),)), {875: 825})
        self.assertEqual([c.service_id for c in out[1]], [825])

    def test_services_not_in_the_table_are_untouched(self) -> None:
        out = W.remap((ev(801, T0, 30), ev(875, T0, 30)), {875: 825})
        self.assertEqual(sorted(e.service_id for e in out[0]), [801, 825])

    def test_an_empty_table_changes_nothing(self) -> None:
        goc = (ev(875, T0, 30),)
        self.assertEqual(W.remap(goc, {})[0], goc)

    def test_the_source_number_may_clash_with_a_real_on_air_service(self) -> None:
        """Hai sổ đánh số khác nhau: 875 của bên cấp lịch ≠ 875 của SDT.

        Trên hệ thật, SDT có dịch vụ 875 là QUANG NGAI 2 RADIO — không liên
        quan gì tới Quảng Trị. Phép đổi tra theo số của **nguồn**, và chạy
        trước mọi bước khác, nên chuyện trùng số này không bao giờ lẫn được.
        """
        out = W.remap(((ev(875, T0, 30, "lich Quang Tri"),), ()), {875: 825})
        self.assertEqual([(e.service_id, e.name) for e in out[0]],
                         [(825, "lich Quang Tri")])

    def test_build_renames_before_merging(self) -> None:
        """Đổi số phải xảy ra TRƯỚC khi gộp, nếu không hai đợt của cùng một
        kênh bị coi là hai kênh và cả hai cùng lên sóng."""
        cu_ = ((ev(875, T0, 60, "ban cu"),), (phu(875, T0, 24),))
        moi_ = ((ev(875, T0 + timedelta(minutes=30), 60, "ban moi"),),
                (phu(875, T0, 24),))
        out = W.build([cu_, moi_], T0 - timedelta(hours=1), mapping={875: 825})
        self.assertEqual([(e.service_id, e.name) for e in out],
                         [(825, "ban moi")])

    def test_without_the_table_the_channel_is_filtered_away(self) -> None:
        """Chứng minh hậu quả của việc KHÔNG khai: kênh biến mất khỏi EPG."""
        su_kien = W.build([((ev(875, T0, 60),), ())], T0 - timedelta(hours=1))
        giu, bo = W.only_services(su_kien, {825})
        self.assertEqual(giu, ())
        self.assertEqual(bo, (875,))

        su_kien = W.build([((ev(875, T0, 60),), ())], T0 - timedelta(hours=1),
                          mapping={875: 825})
        giu, bo = W.only_services(su_kien, {825})
        self.assertEqual([e.service_id for e in giu], [825])
        self.assertEqual(bo, ())


class TestLichSauKhoangTrong(unittest.TestCase):
    """``far_future`` — báo phần lịch nằm sau một khoảng trống dài.

    Thật: file lịch 2026-09-14 mang 292 sự kiện đề ngày 2 và 3 tháng 10, toàn
    bộ thuộc dịch vụ 838, trong khi 16/9 tới 1/10 trống trơn. Bên cấp lịch xác
    nhận là lỗi nhập liệu.
    """

    TRUOC = T0 - timedelta(hours=1)

    def test_a_continuous_schedule_raises_nothing(self) -> None:
        lien = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(48))
        self.assertEqual(W.far_future(lien, self.TRUOC), ())

    def test_it_reports_what_sits_after_the_gap(self) -> None:
        than = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(24))
        rac = (ev(838, T0 + timedelta(days=17), 60, "rac"),)
        out = W.far_future(than + rac, self.TRUOC)
        self.assertEqual([e.name for e in out], ["rac"])

    def test_it_does_not_drop_anything(self) -> None:
        """Báo ra, không tự vứt — cùng khuôn với ``reject_overlong``."""
        than = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(24))
        rac = (ev(838, T0 + timedelta(days=17), 60),)
        giu = W.build([than + rac], self.TRUOC, depth_hours=24 * 30)
        self.assertEqual(len(giu), 25)

    def test_gaps_in_the_past_are_ignored(self) -> None:
        """Hộp thư giữ cả lịch cũ; quá khứ đầy khoảng trống hợp lệ.

        Không lọc quá khứ thì trên hộp thư thật cảnh báo kêu 7101 sự kiện trên
        cả 45 kênh — kêu về mọi thứ là không nói gì.
        """
        cu_ky = (ev(801, T0 - timedelta(days=20), 60),)
        nay = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(24))
        self.assertEqual(W.far_future(cu_ky + nay, self.TRUOC), ())

    def test_an_event_in_progress_counts_as_present(self) -> None:
        dang = (ev(801, T0 - timedelta(minutes=30), 60),)
        sau = tuple(ev(801, T0 + timedelta(hours=i), 60) for i in range(1, 24))
        self.assertEqual(W.far_future(dang + sau, T0), ())

    def test_naive_now_refused(self) -> None:
        with self.assertRaises(ValueError):
            W.far_future((ev(801, T0, 60),), datetime(2026, 9, 8))

    def test_the_real_gap_is_two_days(self) -> None:
        """Một ngày rưỡi chưa phải khoảng trống; hai ngày thì phải."""
        than = (ev(801, T0, 60),)
        gan = (ev(801, T0 + timedelta(days=1, hours=12), 60),)
        xa = (ev(801, T0 + timedelta(days=2, hours=1), 60),)
        self.assertEqual(W.far_future(than + gan, self.TRUOC), ())
        self.assertEqual(len(W.far_future(than + xa, self.TRUOC)), 1)


class TestClip(unittest.TestCase):
    def test_keeps_event_in_progress(self) -> None:
        """Sự kiện đang phát dở vẫn cần cho p/f, không được cắt."""
        running = ev(801, T0 - timedelta(minutes=10), 30)
        self.assertEqual(W.clip((running,), T0), (running,))

    def test_drops_event_finished_on_an_earlier_day(self) -> None:
        past = ev(801, T0 - timedelta(hours=2), 30)   # hom truoc, T0 la 00:00 UTC
        self.assertEqual(W.clip((past,), T0), ())

    def test_drops_event_beyond_the_window(self) -> None:
        far = ev(801, T0 + timedelta(hours=200), 30)
        self.assertEqual(W.clip((far,), T0), ())
        self.assertEqual(len(W.clip((far,), T0, depth_hours=240)), 1)

    def test_naive_now_refused(self) -> None:
        with self.assertRaises(ValueError):
            W.clip((), datetime(2026, 9, 8))


class TestClipGiuTronNgay(unittest.TestCase):
    """Mép đầu cửa sổ là **00:00 UTC hôm nay**, không phải ``now``.

    EIT schedule sub-table 0x50 phủ "ngày 0–3"; ngày 0 bắt đầu 00:00 UTC. Cắt
    ở ``now`` là phát ra một ngày 0 khuyết đầu. Hai bản thu Barrowa cách nhau
    bốn tiếng đều bắt đầu đúng 00:00:00 UTC.
    """

    TRUA = T0 + timedelta(hours=12)      # 2026-09-08 12:00 UTC

    def test_a_programme_finished_earlier_today_is_kept(self) -> None:
        xong = ev(801, T0 + timedelta(hours=2), 60)   # 02:00-03:00, da xong
        self.assertEqual(W.clip((xong,), self.TRUA), (xong,))

    def test_a_programme_from_yesterday_is_dropped(self) -> None:
        hom_qua = ev(801, T0 - timedelta(hours=3), 60)
        self.assertEqual(W.clip((hom_qua,), self.TRUA), ())

    def test_a_programme_straddling_midnight_is_kept(self) -> None:
        """Bắt đầu hôm qua, kết thúc hôm nay: vẫn thuộc ngày 0."""
        vat = ev(801, T0 - timedelta(minutes=30), 60)
        self.assertEqual(W.clip((vat,), self.TRUA), (vat,))

    def test_the_far_edge_still_moves_with_now(self) -> None:
        """Mép cuối là độ sâu CÒN LẠI; neo vào đầu ngày thì cửa sổ ngắn dần."""
        xa = ev(801, self.TRUA + timedelta(hours=191), 30)
        self.assertEqual(W.clip((xa,), self.TRUA), (xa,))

    def test_day_start_is_utc_midnight_not_hanoi_midnight(self) -> None:
        """Nửa đêm Hà Nội là 17:00 UTC hôm trước — khác hẳn, và Barrowa dùng UTC."""
        self.assertEqual(W.dau_ngay_utc(self.TRUA), T0)

    def test_day_start_converts_other_zones(self) -> None:
        vn = timezone(timedelta(hours=7))
        # 2026-09-08 09:00 gio Ha Noi = 02:00 UTC cung ngay
        self.assertEqual(W.dau_ngay_utc(datetime(2026, 9, 8, 9, 0, tzinfo=vn)), T0)

    def test_naive_now_refused(self) -> None:
        with self.assertRaises(ValueError):
            W.dau_ngay_utc(datetime(2026, 9, 8))


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
