"""Quy tắc version và phép kiểm tra trước khi đấu nối — RO-1, FR-15/17/18.

Đây là rủi ro lớn nhất của cả dự án: sai version thì hoặc cả mạng dò lại kênh,
hoặc — tệ hơn — đầu thu **không nhận ra có gì đổi** và giữ dữ liệu cũ, im
lặng, cho tới khi có người gọi điện.

Bài quan trọng nhất là ``test_catches_silent_change``: nó dựng đúng tình huống
đó trên cấu hình thật và đòi hệ chặn lại.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import seed
from vtcsi.config import loader
from vtcsi.model import version as V
from vtcsi.tables import tsduck as T
from vtcsi.version import preflight

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"
CONFIG = Path(__file__).parent.parent / "config"


def _air():
    if not GOLDEN.exists():
        raise unittest.SkipTest("khong tim thay chuan vang")
    return T.read_dump(GOLDEN.read_text(encoding="utf-8"))


def _cfg():
    """Ban gieo **da commit**, khong phai thu muc dang sua.

    Xem ``tests/seed.py``. Doc thang ``config/`` thi moi lan nguoi van hanh
    tang mot version la ba bai o duoi do — dung luc ho dang lam dung.
    """
    td = seed.committed_config()
    try:
        return loader.load(Path(td.name) / "config")
    finally:
        td.cleanup()


class TestFieldWidth(unittest.TestCase):
    """Trường rộng 5 bit — chỗ người ta hay nhớ nhầm thành 'tới 32'."""

    def test_valid_range(self) -> None:
        self.assertEqual(V.validate(0), 0)
        self.assertEqual(V.validate(31), 31)
        self.assertEqual(V.MAX, 31)

    def test_thirty_two_is_out_of_range(self) -> None:
        with self.assertRaises(V.VersionError) as ctx:
            V.validate(32)
        self.assertIn("0…31", str(ctx.exception))

    def test_negative_refused(self) -> None:
        with self.assertRaises(V.VersionError):
            V.validate(-1)

    def test_bool_is_not_an_int_here(self) -> None:
        with self.assertRaises(V.VersionError):
            V.validate(True)


class TestSuccessor(unittest.TestCase):
    def test_plain_increment(self) -> None:
        self.assertEqual(V.next_version(4), 5)
        self.assertEqual(V.next_version(30), 31)

    def test_wraps_after_31(self) -> None:
        """Sau 31 là 0, không phải 32 — và 0 là bước hợp lệ."""
        self.assertEqual(V.next_version(31), 0)
        self.assertTrue(V.is_successor(0, 31))

    def test_full_cycle_visits_every_value_once(self) -> None:
        seen, v = [], 0
        for _ in range(V.MODULUS):
            seen.append(v)
            v = V.next_version(v)
        self.assertEqual(sorted(seen), list(range(V.MODULUS)))
        self.assertEqual(v, 0, "di het mot vong phai ve cho cu")

    def test_not_a_successor(self) -> None:
        self.assertFalse(V.is_successor(7, 4))
        self.assertFalse(V.is_successor(4, 4))
        self.assertFalse(V.is_successor(3, 4))


class TestClassify(unittest.TestCase):
    """Bảng phán quyết — bốn ô, mỗi ô một hệ quả khác nhau trên sóng."""

    def test_in_sync(self) -> None:
        self.assertIs(
            V.classify(config_version=4, air_version=4, content_same=True),
            V.Verdict.IN_SYNC)

    def test_ready_to_apply(self) -> None:
        self.assertIs(
            V.classify(config_version=5, air_version=4, content_same=False),
            V.Verdict.READY)

    def test_pointless_bump(self) -> None:
        """Tăng version mà nội dung không đổi: cả mạng dò lại kênh vô ích."""
        self.assertIs(
            V.classify(config_version=5, air_version=4, content_same=True),
            V.Verdict.POINTLESS_BUMP)

    def test_silent_change_is_the_dangerous_one(self) -> None:
        v = V.classify(config_version=4, air_version=4, content_same=False)
        self.assertIs(v, V.Verdict.SILENT_CHANGE)
        self.assertIn(v, V.BLOCKING)

    def test_unexpected_jump(self) -> None:
        v = V.classify(config_version=9, air_version=4, content_same=False)
        self.assertIs(v, V.Verdict.UNEXPECTED_JUMP)
        self.assertIn(v, V.BLOCKING)

    def test_wrap_is_not_treated_as_a_jump(self) -> None:
        """31 -> 0 là bước bình thường, không được coi là bất thường."""
        self.assertIs(
            V.classify(config_version=0, air_version=31, content_same=False),
            V.Verdict.READY)

    def test_only_two_verdicts_block(self) -> None:
        self.assertEqual(V.BLOCKING,
                         {V.Verdict.SILENT_CHANGE, V.Verdict.UNEXPECTED_JUMP})

    def test_explanations_name_the_next_value(self) -> None:
        msg = V.explain(V.Verdict.SILENT_CHANGE, config_version=4, air_version=4)
        self.assertIn("5", msg)


class TestDescribeMove(unittest.TestCase):
    """Câu nói cho người vận hành đọc trước khi bấm.

    Ba loại bước có ba hệ quả khác nhau, nên chúng phải đọc ra khác nhau. Và
    **lùi lại là hợp lệ**: đầu thu phát hiện version *đổi* chứ không phải
    *tăng*, vì trường 5 bit quay vòng nên không có thứ tự tuyệt đối.
    """

    def test_a_step_forward(self) -> None:
        self.assertIn("bước kế tiếp", V.describe_move(5, 6))

    def test_a_step_back(self) -> None:
        self.assertIn("lùi lại", V.describe_move(6, 5))

    def test_a_far_jump(self) -> None:
        self.assertIn("nhảy xa", V.describe_move(5, 12))

    def test_no_move_at_all(self) -> None:
        self.assertIn("giữ nguyên", V.describe_move(5, 5))

    def test_it_wraps_forward(self) -> None:
        self.assertIn("bước kế tiếp", V.describe_move(31, 0))

    def test_it_wraps_backward(self) -> None:
        self.assertIn("lùi lại", V.describe_move(0, 31))

    def test_both_numbers_appear(self) -> None:
        for a, b in ((5, 6), (6, 5), (5, 12), (31, 0)):
            with self.subTest(a=a, b=b):
                text = V.describe_move(a, b)
                self.assertIn(str(a), text)
                self.assertIn(str(b), text)

    def test_out_of_range_is_refused_on_either_side(self) -> None:
        with self.assertRaises(V.VersionError):
            V.describe_move(5, 32)
        with self.assertRaises(V.VersionError):
            V.describe_move(-1, 5)


class TestPreflightOnRealConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = _cfg()
        cls.air = _air()

    def test_seeded_config_is_in_sync(self) -> None:
        report = preflight.check(self.cfg, self.air)
        self.assertTrue(report.ok, report.text())
        self.assertEqual(len(report.rows), 10)
        self.assertTrue(all(r.verdict is V.Verdict.IN_SYNC for r in report.rows))

    def test_catches_silent_change(self) -> None:
        """Đổi tên một kênh mà quên tăng version SDT — phải bị chặn."""
        sdts = list(self.cfg.sdts)
        i = next(j for j, s in enumerate(sdts) if s.ts_id == 8)
        services = list(sdts[i].services)
        services[0] = replace(services[0], name="TEN MOI")
        sdts[i] = replace(sdts[i], services=tuple(services))
        broken = replace(self.cfg, sdts=tuple(sdts))

        report = preflight.check(broken, self.air)
        self.assertFalse(report.ok)
        row = next(r for r in report.rows if r.name == "SDT ts8")
        self.assertIs(row.verdict, V.Verdict.SILENT_CHANGE)
        self.assertIn("SDT ts8", report.text())

    def test_correct_change_passes(self) -> None:
        """Cùng thay đổi đó nhưng có tăng version thì đi qua được."""
        sdts = list(self.cfg.sdts)
        i = next(j for j, s in enumerate(sdts) if s.ts_id == 8)
        services = list(sdts[i].services)
        services[0] = replace(services[0], name="TEN MOI")
        sdts[i] = replace(sdts[i], services=tuple(services),
                          version=V.next_version(sdts[i].version))
        fixed = replace(self.cfg, sdts=tuple(sdts))

        report = preflight.check(fixed, self.air)
        self.assertTrue(report.ok, report.text())
        row = next(r for r in report.rows if r.name == "SDT ts8")
        self.assertIs(row.verdict, V.Verdict.READY)

    def test_catches_pointless_bump(self) -> None:
        bumped = replace(self.cfg,
                         network=replace(self.cfg.network,
                                         version=V.next_version(self.cfg.network.version)))
        report = preflight.check(bumped, self.air)
        row = next(r for r in report.rows if r.name == "NIT")
        self.assertIs(row.verdict, V.Verdict.POINTLESS_BUMP)
        self.assertTrue(report.ok, "tang thua thi canh bao, khong chan")

    def test_catches_unexpected_jump(self) -> None:
        jumped = replace(self.cfg,
                         network=replace(self.cfg.network, version=20))
        report = preflight.check(jumped, self.air)
        self.assertFalse(report.ok)
        row = next(r for r in report.rows if r.name == "NIT")
        self.assertIs(row.verdict, V.Verdict.UNEXPECTED_JUMP)

    def test_missing_table_is_blocking(self) -> None:
        fewer = replace(self.cfg, bouquets=self.cfg.bouquets[1:])
        report = preflight.check(fewer, self.air)
        self.assertFalse(report.ok)
        missing = [r for r in report.rows if r.verdict is None]
        self.assertEqual(len(missing), 1)
        self.assertIn("THIEU", missing[0].line())

    def test_version_is_not_counted_as_content(self) -> None:
        """Đổi mỗi version thì nội dung phải vẫn được coi là giống nhau."""
        bumped = replace(self.cfg,
                         network=replace(self.cfg.network,
                                         version=V.next_version(self.cfg.network.version)))
        row = next(r for r in preflight.check(bumped, self.air).rows if r.name == "NIT")
        self.assertTrue(row.content_same)


if __name__ == "__main__":
    unittest.main()
