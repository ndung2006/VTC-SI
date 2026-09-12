"""Luật số kênh — ``model.lcn``.

Hai nhóm bài quan trọng hơn phần còn lại:

* ``TestFalseAlarmsAreSuppressed`` — cảnh báo luôn kêu là cảnh báo bị tắt.
  FR-54 đã bị rút khỏi đặc tả vì đúng lý do đó; bài này giữ cho bài học ấy
  không bị quên khi ai đó "cải tiến" ``check``.
* ``TestTheSeededConfigIsAudited`` — chạy luật lên đúng cấu hình đã gieo từ
  sóng. Đây là chỗ luật gặp dữ liệu thật, và là chỗ nó tìm ra kênh 877.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import seed
from vtcsi.config import loader
from vtcsi.model import lcn
from vtcsi.model.entities import (
    Bouquet,
    BatTsLoop,
    Config,
    LcnEntry,
    Network,
    NitTsLoop,
    SdtTable,
    Service,
    ServiceRef,
    ServiceType,
)

#: Thu muc cau hinh **da commit**, khong phai thu muc dang sua.
#:
#: Nguoi van hanh sua `config/` moi ngay — do la muc dich cua no. Bai test nao
#: khang dinh mot su that ve *ban gieo* ma lai doc thu muc lam viec thi se do
#: len vao dung luc ho lam dung. Xem `tests/seed.py`.
#: (giu ten CONFIG cho cac bai khong lien quan)
CONFIG = Path(__file__).parent.parent / "config"


def svc(sid: int, name: str = "KENH", kind: int = 1) -> Service:
    return Service(service_id=sid, name=name, provider="VTC",
                   service_type=ServiceType(kind))


def tiny(numbers: dict[int, int] | None = None,
         members: tuple[int, ...] = (10, 11, 12)) -> Config:
    """Một cấu hình nhỏ nhất còn hợp lệ: một TS, ba kênh, một bouquet."""
    numbers = {} if numbers is None else numbers
    services = tuple(svc(s) for s in members)
    return Config(
        network=Network(network_id=1, name="N", version=0, ts_loops=(
            NitTsLoop(ts_id=5, original_network_id=1,
                      services=tuple(ServiceRef(s, 1) for s in members)),)),
        sdts=(SdtTable(ts_id=5, original_network_id=1, version=0, actual=True,
                       services=services),),
        bouquets=(Bouquet(bouquet_id=0x0100, name="B", version=0, ts_loops=(
            BatTsLoop(ts_id=5, original_network_id=1,
                      services=tuple(ServiceRef(s, 1) for s in members),
                      # PDS co mat dung khi co so kenh — bat bien that tren song,
                      # va la thu `check` doi hoi.
                      private_data_specifier="NorDig" if numbers else None,
                      lcn=tuple(LcnEntry(s, n) for s, n in sorted(numbers.items()))),
        )),),
    )


def only(cfg: Config) -> Bouquet:
    return cfg.bouquets[0]


class TestCheckFindsRealFaults(unittest.TestCase):
    def test_clean_config_says_nothing(self) -> None:
        self.assertEqual(lcn.check(tiny({10: 1, 11: 2, 12: 3})), ())

    def test_two_services_on_one_number_is_blocking(self) -> None:
        got = lcn.blocking(lcn.check(tiny({10: 7, 11: 7, 12: 3})))
        self.assertEqual(len(got), 1)
        self.assertIn("số kênh 7", got[0].message)
        self.assertIn("10", got[0].message)
        self.assertIn("11", got[0].message)

    def test_three_services_on_one_number_is_one_problem_not_three(self) -> None:
        got = lcn.blocking(lcn.check(tiny({10: 7, 11: 7, 12: 7})))
        self.assertEqual(len(got), 1)
        self.assertIn("3 dịch vụ", got[0].message)

    def test_number_above_ten_bits_is_blocking(self) -> None:
        cfg = tiny({10: 1})
        b = only(cfg)
        broken = replace(b, ts_loops=(replace(
            b.ts_loops[0], lcn=(LcnEntry(10, 1024),)),))
        got = lcn.blocking(lcn.check(replace(cfg, bouquets=(broken,))))
        self.assertTrue(any("ngoài khoảng" in p.message for p in got))

    def test_number_zero_is_blocking(self) -> None:
        cfg = tiny({10: 1})
        b = only(cfg)
        broken = replace(b, ts_loops=(replace(
            b.ts_loops[0], lcn=(LcnEntry(10, 0),)),))
        self.assertTrue(lcn.blocking(lcn.check(replace(cfg, bouquets=(broken,)))))

    def test_number_pointing_at_a_non_member_is_blocking(self) -> None:
        cfg = tiny({10: 1})
        b = only(cfg)
        loop = b.ts_loops[0]
        broken = replace(b, ts_loops=(replace(
            loop, lcn=loop.lcn + (LcnEntry(999, 5),)),))
        got = lcn.blocking(lcn.check(replace(cfg, bouquets=(broken,))))
        self.assertTrue(any("999" in p.message for p in got))

    def test_member_without_a_number_is_reported_but_not_blocking(self) -> None:
        got = lcn.check(tiny({10: 1, 11: 2}))  # 12 khong co so
        self.assertEqual(len(got), 1)
        self.assertFalse(got[0].blocking)
        self.assertIn("12", got[0].message)


class TestDuplicatesAcrossTransportStreams(unittest.TestCase):
    """Khách hàng bấm số 7 trên điều khiển; họ không biết TS là gì."""

    def _two_ts(self, a: int, b: int) -> Config:
        cfg = tiny({10: a})
        bq = only(cfg)
        second = BatTsLoop(ts_id=6, original_network_id=1,
                           services=(ServiceRef(20, 1),),
                           private_data_specifier="NorDig",
                           lcn=(LcnEntry(20, b),))
        cfg = replace(cfg, sdts=cfg.sdts + (
            SdtTable(ts_id=6, original_network_id=1, version=0, actual=False,
                     services=(svc(20),)),))
        return replace(cfg, bouquets=(replace(bq, ts_loops=bq.ts_loops + (second,)),))

    def test_same_number_in_two_transport_streams_is_blocking(self) -> None:
        got = lcn.blocking(lcn.check(self._two_ts(7, 7)))
        self.assertTrue(any("dùng chung" in p.message for p in got))

    def test_different_numbers_are_fine(self) -> None:
        self.assertEqual(lcn.blocking(lcn.check(self._two_ts(7, 8))), ())


class TestFalseAlarmsAreSuppressed(unittest.TestCase):
    """Một cảnh báo luôn kêu là một cảnh báo đã bị tắt — bài học từ FR-54."""

    def test_bouquet_with_no_numbers_at_all_is_left_alone(self) -> None:
        """0x6550 gom 48 dịch vụ de khoa ma, khong phai de danh so."""
        self.assertEqual(lcn.check(tiny({})), ())

    def test_but_a_bouquet_that_numbers_some_is_checked(self) -> None:
        self.assertEqual(len(lcn.check(tiny({10: 1}))), 2)  # 11 va 12 thieu so


class TestPrivateDataSpecifier(unittest.TestCase):
    """Kieu hong im lang nhat: co so kenh nhung khong khai PDS.

    Cau hinh van nap duoc, XML van sinh ra, bang van phat. Dau thu nhan
    descriptor `0x83` ma khong biet no thuoc dac ta rieng nao, nen bo qua ca
    khoi — va **ca bang so kenh bien mat** mà khong co dau hieu gi.
    """

    def _loop(self, pds):
        cfg = tiny({10: 1, 11: 2, 12: 3})
        b = only(cfg)
        made = replace(b, ts_loops=(replace(
            b.ts_loops[0], private_data_specifier=pds),))
        return replace(cfg, bouquets=(made,))

    def test_numbers_without_a_specifier_is_blocking(self) -> None:
        got = lcn.blocking(lcn.check(self._loop(None)))
        self.assertEqual(len(got), 1)
        self.assertIn("private_data_specifier", got[0].message)
        self.assertIn("3 số kênh", got[0].message)

    def test_numbers_with_a_specifier_are_fine(self) -> None:
        self.assertEqual(lcn.check(self._loop("NorDig")), ())

    def test_a_specifier_without_numbers_is_harmless(self) -> None:
        """Chieu nguoc lai chi ton vai byte — khong dang keu."""
        cfg = tiny({})
        b = only(cfg)
        made = replace(b, ts_loops=(replace(
            b.ts_loops[0], private_data_specifier="NorDig"),))
        self.assertEqual(lcn.check(replace(cfg, bouquets=(made,))), ())

    def test_a_grouping_bouquet_needs_no_specifier(self) -> None:
        """0x6550 co ba vong, khong so kenh nao, khong PDS nao — va dung the."""
        self.assertEqual(lcn.check(tiny({})), ())


class TestSetNumbers(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = tiny({10: 1, 11: 2, 12: 3})
        self.b = only(self.cfg)

    def test_renumbering_writes_the_new_table(self) -> None:
        out = lcn.set_numbers(self.b, 5, {10: 5, 11: 6, 12: 7})
        self.assertEqual([e.lcn for e in out.ts_loops[0].lcn], [5, 6, 7])

    def test_entries_come_out_sorted_by_service(self) -> None:
        out = lcn.set_numbers(self.b, 5, {12: 1, 10: 2, 11: 3})
        self.assertEqual([e.service_id for e in out.ts_loops[0].lcn], [10, 11, 12])

    def test_omitting_a_service_drops_its_number(self) -> None:
        out = lcn.set_numbers(self.b, 5, {10: 1, 11: 2})
        self.assertEqual([e.service_id for e in out.ts_loops[0].lcn], [10, 11])

    def test_visibility_is_kept_when_not_mentioned(self) -> None:
        hidden = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0],
            lcn=(LcnEntry(10, 1, visible=False), LcnEntry(11, 2))),))
        out = lcn.set_numbers(hidden, 5, {10: 1, 11: 2})
        self.assertFalse(out.ts_loops[0].lcn[0].visible)

    def test_visibility_can_be_changed(self) -> None:
        out = lcn.set_numbers(self.b, 5, {10: 1}, {10: False})
        self.assertFalse(out.ts_loops[0].lcn[0].visible)

    def test_duplicate_inside_the_form_is_refused(self) -> None:
        with self.assertRaises(lcn.LcnError) as e:
            lcn.set_numbers(self.b, 5, {10: 4, 11: 4})
        self.assertIn("số kênh 4", str(e.exception))

    def test_out_of_range_is_refused(self) -> None:
        for bad in (0, -1, 1024, 70000):
            with self.subTest(n=bad), self.assertRaises(lcn.LcnError):
                lcn.set_numbers(self.b, 5, {10: bad})

    def test_numbering_a_non_member_is_refused(self) -> None:
        with self.assertRaises(lcn.LcnError):
            lcn.set_numbers(self.b, 5, {999: 4})

    def test_unknown_transport_stream_is_refused(self) -> None:
        with self.assertRaises(lcn.LcnError):
            lcn.set_numbers(self.b, 99, {10: 1})

    def test_a_refused_edit_changes_nothing(self) -> None:
        before = self.b
        with self.assertRaises(lcn.LcnError):
            lcn.set_numbers(self.b, 5, {10: 4, 11: 4})
        self.assertEqual(before, self.b)

    def test_clash_with_another_transport_stream_is_refused(self) -> None:
        second = BatTsLoop(ts_id=6, original_network_id=1,
                           services=(ServiceRef(20, 1),), lcn=(LcnEntry(20, 9),))
        two = replace(self.b, ts_loops=self.b.ts_loops + (second,))
        with self.assertRaises(lcn.LcnError) as e:
            lcn.set_numbers(two, 5, {10: 9})
        self.assertIn("TS 6", str(e.exception))

    def test_the_result_passes_its_own_audit(self) -> None:
        out = lcn.set_numbers(self.b, 5, {10: 11, 11: 12, 12: 13})
        self.assertEqual(lcn.check(replace(self.cfg, bouquets=(out,))), ())


class TestMembership(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = tiny({10: 1, 11: 2}, members=(10, 11, 12))
        self.b = only(self.cfg)

    def test_adding_a_service_already_present_is_refused(self) -> None:
        with self.assertRaises(lcn.LcnError):
            lcn.add_member(self.b, 5, ServiceRef(10, 1), 9)

    def test_adding_then_numbering(self) -> None:
        smaller = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=(ServiceRef(10, 1), ServiceRef(11, 1))),))
        out = lcn.add_member(smaller, 5, ServiceRef(12, 1), 3)
        self.assertIn(12, {r.service_id for r in out.ts_loops[0].services})
        self.assertEqual({e.service_id: e.lcn for e in out.ts_loops[0].lcn},
                         {10: 1, 11: 2, 12: 3})

    def test_adding_without_a_number_leaves_it_unnumbered(self) -> None:
        smaller = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=(ServiceRef(10, 1), ServiceRef(11, 1))),))
        out = lcn.add_member(smaller, 5, ServiceRef(12, 1))
        self.assertNotIn(12, {e.service_id for e in out.ts_loops[0].lcn})

    def test_adding_with_a_taken_number_is_refused(self) -> None:
        smaller = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=(ServiceRef(10, 1), ServiceRef(11, 1))),))
        with self.assertRaises(lcn.LcnError):
            lcn.add_member(smaller, 5, ServiceRef(12, 1), 1)

    def test_a_new_member_goes_on_the_end(self) -> None:
        smaller = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=(ServiceRef(11, 1), ServiceRef(12, 1)),
            lcn=()),))
        out = lcn.add_member(smaller, 5, ServiceRef(10, 1))
        self.assertEqual([r.service_id for r in out.ts_loops[0].services],
                         [11, 12, 10])

    def test_the_existing_order_is_never_rearranged(self) -> None:
        """Thu tu tren song KHONG theo so dich vu, va phai giu nguyen.

        Vong TS 8 cua bouquet 0x6510 dang phat theo thu tu [815, 856, 826, …].
        Sap lai cho dep se doi byte cua `service_list_descriptor`, tuc pha AC-1,
        va lam `git diff` phinh tu mot dong len ca tram dong.
        """
        scrambled = (ServiceRef(815, 1), ServiceRef(856, 2), ServiceRef(826, 1))
        b = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=scrambled, lcn=()),))
        out = lcn.add_member(b, 5, ServiceRef(801, 1))
        self.assertEqual([r.service_id for r in out.ts_loops[0].services],
                         [815, 856, 826, 801])

    def test_removing_does_not_rearrange_either(self) -> None:
        scrambled = (ServiceRef(815, 1), ServiceRef(856, 2), ServiceRef(826, 1))
        b = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=scrambled, lcn=()),))
        out = lcn.remove_member(b, 5, 856)
        self.assertEqual([r.service_id for r in out.ts_loops[0].services],
                         [815, 826])

    def test_remove_then_add_puts_it_back_at_the_end_not_in_place(self) -> None:
        """Ghi ro hanh vi nay de khong ai bat ngo.

        Bo mot kenh roi them lai KHONG tra no ve cho cu. Neu can dung thu tu
        cu tung byte, cach dung la `git checkout` chu khong phai bam lai.
        """
        scrambled = (ServiceRef(815, 1), ServiceRef(856, 2), ServiceRef(826, 1))
        b = replace(self.b, ts_loops=(replace(
            self.b.ts_loops[0], services=scrambled, lcn=()),))
        out = lcn.add_member(lcn.remove_member(b, 5, 856), 5, ServiceRef(856, 2))
        self.assertEqual([r.service_id for r in out.ts_loops[0].services],
                         [815, 826, 856])

    def test_removing_takes_the_number_with_it(self) -> None:
        out = lcn.remove_member(self.b, 5, 10)
        self.assertNotIn(10, {r.service_id for r in out.ts_loops[0].services})
        self.assertNotIn(10, {e.service_id for e in out.ts_loops[0].lcn})

    def test_removing_leaves_no_dangling_number(self) -> None:
        out = lcn.remove_member(self.b, 5, 10)
        self.assertEqual(lcn.blocking(lcn.check(
            replace(self.cfg, bouquets=(out,)))), ())

    def test_removing_someone_not_there_is_refused(self) -> None:
        with self.assertRaises(lcn.LcnError):
            lcn.remove_member(self.b, 5, 999)


class TestNextFree(unittest.TestCase):
    def test_first_gap(self) -> None:
        self.assertEqual(lcn.next_free(only(tiny({10: 1, 11: 2, 12: 4}))), 3)

    def test_gap_after_a_floor(self) -> None:
        self.assertEqual(lcn.next_free(only(tiny({10: 1, 11: 2, 12: 4})), 4), 5)

    def test_after_last_does_not_fill_gaps(self) -> None:
        """Mot lo hong thuong la cho de danh, khong phai cho trong."""
        self.assertEqual(lcn.next_after_last(only(tiny({10: 1, 11: 2, 12: 4}))), 5)

    def test_empty_bouquet_starts_at_one(self) -> None:
        self.assertEqual(lcn.next_after_last(only(tiny({}))), 1)

    def test_running_out_is_an_error_not_a_wrong_answer(self) -> None:
        cfg = tiny({10: lcn.MAX_LCN})
        with self.assertRaises(lcn.LcnError):
            lcn.next_free(only(cfg), lcn.MAX_LCN)


class TestForgetService(unittest.TestCase):
    def test_a_deleted_service_leaves_no_trace(self) -> None:
        cfg = tiny({10: 1, 11: 2, 12: 3})
        out = lcn.forget_service(cfg, 5, 11)
        loop = out.bouquets[0].ts_loops[0]
        self.assertEqual([r.service_id for r in loop.services], [10, 12])
        self.assertEqual([e.service_id for e in loop.lcn], [10, 12])

    def test_forgetting_someone_absent_is_harmless(self) -> None:
        cfg = tiny({10: 1})
        self.assertEqual(lcn.forget_service(cfg, 5, 999), cfg)


class TestTheSeededConfigIsAudited(unittest.TestCase):
    """Luat gap du lieu that — cau hinh gieo tu song dang phat."""

    @classmethod
    def setUpClass(cls) -> None:
        td = seed.committed_config()
        try:
            cls.cfg = loader.load(Path(td.name) / "config")
        finally:
            td.cleanup()
        cls.problems = lcn.check(cls.cfg)

    def test_nothing_blocking_is_on_air(self) -> None:
        """Khong co hai kenh nao trung so — neu co thi la su co dang bao."""
        self.assertEqual([p.text() for p in lcn.blocking(self.problems)], [])

    def test_exactly_one_thing_worth_saying(self) -> None:
        """Neu con so nay nhay len, hoac co loi moi, hoac `check` lai kêu bua."""
        self.assertEqual(len(self.problems), 1,
                         "\n".join(p.text() for p in self.problems))

    def test_it_is_service_877(self) -> None:
        """Kenh 877 CAO BANG RADIO phat ra song ma khong co so kenh."""
        self.assertIn("877", self.problems[0].message)
        self.assertEqual(self.problems[0].bouquet_id, 0x6510)

    def test_the_gap_it_leaves_is_416(self) -> None:
        """19 kenh radio con lai lien mach 397…415 — thieu dung mot so."""
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x6510)
        self.assertEqual(lcn.next_after_last(b), 416)

    def test_fixing_it_would_clear_the_audit(self) -> None:
        b = next(x for x in self.cfg.bouquets if x.bouquet_id == 0x6510)
        loop = next(t for t in b.ts_loops if t.ts_id == 8)
        numbers = {e.service_id: e.lcn for e in loop.lcn}
        numbers[877] = 416
        fixed = lcn.set_numbers(b, 8, numbers)
        after = replace(self.cfg, bouquets=tuple(
            fixed if x.bouquet_id == 0x6510 else x for x in self.cfg.bouquets))
        self.assertEqual(lcn.check(after), ())


if __name__ == "__main__":
    unittest.main()
