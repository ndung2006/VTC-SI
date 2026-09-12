"""Trông chừng ``tsp`` — ``pipeline.supervise``.

Không bài nào dựng tiến trình thật, không bài nào ngủ thật, không bài nào chạm
đĩa. Cả bốn hiệu ứng phụ — ``spawn``, ``now``, ``sleep``, ``exists`` — đều tiêm
vào, nên toàn bộ vòng lặp chạy trong mấy phần nghìn giây và **một sự cố kéo dài
ba ngày mô phỏng được bằng ba dòng**.

Đó không phải mẹo cho nhanh. Nếu phải chờ thật thì bài "chết lặp năm lần rồi
giãn cách chạm trần" tốn hơn một phút, và một bài test tốn một phút là một bài
test sớm muộn bị tắt.

Nhóm đáng chú ý nhất là ``TestRestartingIsNotFree``: nó ghim lấy quyết định
thiết kế quan trọng nhất của module — **đổi nội dung thì không khởi động lại**.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vtcsi.pipeline import supervise as S
from vtcsi.pipeline.tspbuild import Injection, Output, Plan, build

PLAN = Plan(
    nit=Injection("build/nit.xml", 2000),
    sdt_bat=(Injection("build/sdt-ts8.xml", 1000),
             Injection("build/bat-*.xml", 5000)),
    eit_files="build/eit/*.xml",
    ts_id=8,
    output=Output(destination="236.30.239.1:6000", local_address="10.10.30.240"),
)

T0 = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)


class FakeProcess:
    """Tiến trình giả: sống cho tới khi ai đó gọi ``die``."""

    def __init__(self, code: int = 1) -> None:
        self.code: int | None = None
        self._final = code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.code

    def die(self, code: int | None = None) -> None:
        self.code = self._final if code is None else code

    def terminate(self) -> None:
        self.terminated = True
        self.die(143)

    def kill(self) -> None:  # pragma: no cover — chi dung o bai cung dau
        self.killed = True
        self.die(137)

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise TimeoutError
        return self.code


class Rig:
    """Đồng hồ, giấc ngủ và bộ sinh tiến trình do ta cầm trịch."""

    def __init__(self, *, exists: bool = True) -> None:
        self.t = 1000.0
        self.slept = 0.0
        self.spawned: list[list[str]] = []
        self.procs: list[FakeProcess] = []
        self._exists = exists
        self.refreshes = 0
        self.refresh_code = 0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds
        self.slept += seconds

    def clock(self) -> datetime:
        return T0

    def spawn(self, cmd: list[str]) -> FakeProcess:
        self.spawned.append(list(cmd))
        p = FakeProcess()
        self.procs.append(p)
        return p

    def exists(self, path: str) -> bool:
        return self._exists

    def refresh(self, cmd: tuple[str, ...]) -> tuple[int, str]:
        self.refreshes += 1
        return self.refresh_code, "" if self.refresh_code == 0 else "hong roi"

    def supervisor(self, **kw) -> S.Supervisor:
        return S.Supervisor(plan=PLAN, spawn=self.spawn, now=self.now,
                            sleep=self.sleep, clock=self.clock,
                            exists=self.exists, run_refresh=self.refresh, **kw)


def ran(started: float, lifetime: float) -> S.Attempt:
    return S.classify(started, started + lifetime, 0, False)


# --------------------------------------------------------------- phần thuần


class TestClassify(unittest.TestCase):
    def test_a_long_run_that_ends_is_not_a_startup_failure(self) -> None:
        self.assertIs(ran(0, 3600).outcome, S.Outcome.RAN_THEN_DIED)

    def test_dying_immediately_is_a_startup_failure(self) -> None:
        self.assertIs(ran(0, 0.4).outcome, S.Outcome.DIED_ON_STARTUP)

    def test_the_boundary_counts_as_healthy(self) -> None:
        self.assertIs(ran(0, S.MIN_HEALTHY_SECONDS).outcome, S.Outcome.RAN_THEN_DIED)

    def test_our_own_stop_is_never_a_failure(self) -> None:
        a = S.classify(0, 0.1, 143, stopped_by_us=True)
        self.assertIs(a.outcome, S.Outcome.STOPPED_BY_US)


class TestBackoff(unittest.TestCase):
    def test_no_failure_means_no_wait(self) -> None:
        self.assertEqual(S.backoff(0), 0.0)

    def test_it_grows(self) -> None:
        got = [S.backoff(i) for i in range(1, 7)]
        self.assertEqual(got, sorted(got))
        self.assertEqual(got[0], 1.0)

    def test_it_stops_growing(self) -> None:
        """Chan tren la co y: thiet bi du phong khong duoc vang mat lau."""
        self.assertEqual(S.backoff(50), S.BACKOFF_STEPS[-1])
        self.assertEqual(S.backoff(1000), 30.0)

    def test_it_never_gives_up(self) -> None:
        self.assertLess(S.backoff(10_000), 60.0)


class TestFailureCounting(unittest.TestCase):
    def test_empty_history(self) -> None:
        self.assertEqual(S.consecutive_startup_failures([]), 0)

    def test_counts_the_tail_only(self) -> None:
        h = [ran(0, 0.1), ran(1, 0.1), ran(2, 0.1)]
        self.assertEqual(S.consecutive_startup_failures(h), 3)

    def test_a_healthy_run_wipes_the_count(self) -> None:
        """Chay tot sau thang roi chet hai lan KHAC voi khong bao gio dung noi."""
        h = [ran(0, 0.1)] * 9 + [ran(10, 86_400), ran(20, 0.1)]
        self.assertEqual(S.consecutive_startup_failures(h), 1)

    def test_our_own_stop_also_wipes_it(self) -> None:
        h = [ran(0, 0.1), S.classify(1, 1.1, 143, True)]
        self.assertEqual(S.consecutive_startup_failures(h), 0)


class TestHealth(unittest.TestCase):
    def test_running(self) -> None:
        self.assertIs(S.health([], True), S.Health.RUNNING)

    def test_fresh(self) -> None:
        self.assertIs(S.health([], False), S.Health.STARTING)

    def test_retrying(self) -> None:
        self.assertIs(S.health([ran(0, 0.1)], False), S.Health.RETRYING)

    def test_crash_looping(self) -> None:
        h = [ran(i, 0.1) for i in range(S.CRASH_LOOP_AFTER)]
        self.assertIs(S.health(h, False), S.Health.CRASH_LOOPING)

    def test_a_clean_stop_is_just_stopped(self) -> None:
        self.assertIs(S.health([S.classify(0, 1, 0, True)], False), S.Health.STOPPED)


class TestRestartingIsNotFree(unittest.TestCase):
    """Quyet dinh thiet ke quan trong nhat cua module nay.

    Sua ten kenh, sua so kenh, nap lich moi — deu KHONG duoc khoi dong lai.
    ``inject --poll-files`` va ``eitinject --poll-interval`` tu doc lai file.
    Khoi dong lai la mot lan chop nguon, va mux se nhay sang he kia.
    """

    def test_nothing_to_compare_means_start(self) -> None:
        self.assertTrue(S.command_changed(None, ["tsp"]))

    def test_the_same_command_needs_no_restart(self) -> None:
        cmd = build(PLAN, start_time=T0)
        self.assertFalse(S.command_changed(cmd, list(cmd)))

    def test_only_the_timestamp_moving_needs_no_restart(self) -> None:
        """Neu khong bo qua --time thi lan soi nao cung doi khoi dong lai."""
        a = build(PLAN, start_time=T0)
        b = build(PLAN, start_time=datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc))
        self.assertNotEqual(a, b)
        self.assertFalse(S.command_changed(a, b))

    def test_a_new_output_address_does_need_a_restart(self) -> None:
        from dataclasses import replace
        other = replace(PLAN, output=replace(PLAN.output,
                                             destination="236.30.239.2:6000"))
        self.assertTrue(S.command_changed(build(PLAN, start_time=T0),
                                          build(other, start_time=T0)))

    def test_a_new_transport_stream_does_need_a_restart(self) -> None:
        from dataclasses import replace
        more = replace(PLAN, sdt_bat=PLAN.sdt_bat + (
            Injection("build/sdt-ts3.xml", 5000),))
        self.assertTrue(S.command_changed(build(PLAN, start_time=T0),
                                          build(more, start_time=T0)))

    def test_a_new_repetition_rate_does_need_a_restart(self) -> None:
        from dataclasses import replace
        faster = replace(PLAN, nit=Injection("build/nit.xml", 1000))
        self.assertTrue(S.command_changed(build(PLAN, start_time=T0),
                                          build(faster, start_time=T0)))


class TestMissingInputs(unittest.TestCase):
    def test_all_present(self) -> None:
        self.assertEqual(S.missing_inputs(PLAN, lambda p: True), [])

    def test_all_absent_but_wildcards_are_forgiven(self) -> None:
        gap = S.missing_inputs(PLAN, lambda p: False)
        self.assertEqual(gap, ["build/nit.xml", "build/sdt-ts8.xml"])
        self.assertNotIn("build/bat-*.xml", gap)

    def test_one_missing_is_named(self) -> None:
        self.assertEqual(
            S.missing_inputs(PLAN, lambda p: p != "build/nit.xml"),
            ["build/nit.xml"])


# ------------------------------------------------------------------- vòng lặp


class TestStarting(unittest.TestCase):
    def test_it_spawns_tsp(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        self.assertTrue(sup.start())
        self.assertEqual(len(rig.spawned), 1)
        self.assertEqual(rig.spawned[0][0], "tsp")

    def test_it_refuses_when_tables_are_missing(self) -> None:
        rig = Rig(exists=False)
        sup = rig.supervisor()
        self.assertFalse(sup.start())
        self.assertEqual(rig.spawned, [])

    def test_the_timestamp_is_recomputed_at_every_start(self) -> None:
        """Dung lai moc cu sau ba ngay nghia la phat EPG lech ba ngay."""
        moments = [T0, datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)]
        rig = Rig()
        sup = rig.supervisor()
        sup.clock = lambda: moments.pop(0)
        sup.start()
        sup.child = None
        sup.start()
        first = rig.spawned[0][rig.spawned[0].index("--time") + 1]
        second = rig.spawned[1][rig.spawned[1].index("--time") + 1]
        self.assertNotEqual(first, second)
        self.assertIn("2026/09/14", second)


class TestReaping(unittest.TestCase):
    def test_a_live_child_is_not_reaped(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        sup.start()
        self.assertIsNone(sup.reap())
        self.assertIsNotNone(sup.child)

    def test_a_dead_child_lands_in_the_history(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        sup.start()
        rig.t += 100
        rig.procs[0].die(2)
        attempt = sup.reap()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.exit_code, 2)
        self.assertIs(attempt.outcome, S.Outcome.RAN_THEN_DIED)
        self.assertIsNone(sup.child)


class TestTheLoop(unittest.TestCase):
    def test_it_restarts_a_child_that_dies(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        rounds = [0]

        def until() -> bool:
            rounds[0] += 1
            if rounds[0] == 3 and rig.procs:
                rig.t += 600
                rig.procs[-1].die(1)
            return rounds[0] > 8

        sup.run(until=until)
        self.assertGreaterEqual(len(rig.spawned), 2)

    def test_a_crash_loop_backs_off_instead_of_spinning(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        rounds = [0]

        def until() -> bool:
            rounds[0] += 1
            for p in rig.procs:
                if p.poll() is None:
                    p.die(1)          # chet ngay, khong kip song
            return rounds[0] > 40

        sup.run(until=until)
        self.assertIs(sup.state, S.Health.CRASH_LOOPING)
        self.assertGreater(rig.slept, 0, "chet lap ma khong cho — quay vong khong")

    def test_missing_tables_do_not_spin_the_cpu(self) -> None:
        rig = Rig(exists=False)
        sup = rig.supervisor()
        rounds = [0]

        def until() -> bool:
            rounds[0] += 1
            return rounds[0] > 12

        sup.run(until=until)
        self.assertEqual(rig.spawned, [])
        self.assertGreater(rig.slept, 0, "thieu file ma quay vong khong")

    def test_stopping_terminates_the_child(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        rounds = [0]
        sup.run(until=lambda: (rounds.__setitem__(0, rounds[0] + 1),
                               rounds[0] > 3)[1])
        self.assertTrue(rig.procs[0].terminated)
        self.assertIsNone(sup.child)

    def test_our_own_stop_is_not_counted_as_a_failure(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        rounds = [0]
        sup.run(until=lambda: (rounds.__setitem__(0, rounds[0] + 1),
                               rounds[0] > 3)[1])
        self.assertEqual(S.consecutive_startup_failures(sup.history), 0)


class TestWatching(unittest.TestCase):
    """Sinh lại **ngay khi có thay đổi**, không chờ hết chu kỳ.

    File lịch bàn giao về lúc 8 giờ sáng thì phải lên sóng lúc 8 giờ sáng,
    không phải 9 giờ. Chu kỳ một giờ chỉ là lưới an toàn cho việc cửa sổ EIT
    trôi theo thời gian.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.hop = Path(self._tmp.name) / "inbox"
        self.hop.mkdir()
        (self.hop / "ngay-1.xml").write_text("<PSI/>", encoding="utf-8")
        self.rig = Rig()
        self.sup = self.rig.supervisor(refresh=("vtcsi", "refresh"),
                                       watch=(self.hop,), watch_every=5.0,
                                       refresh_every=3600.0)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def them_file(self, ten: str = "ngay-2.xml") -> None:
        (self.hop / ten).write_text("<PSI/>", encoding="utf-8")

    def test_the_first_run_always_happens(self) -> None:
        """Phai co bang truoc khi dung tsp."""
        self.assertTrue(self.sup.maybe_refresh())
        self.assertEqual(self.rig.refreshes, 1)

    def test_nothing_changed_means_no_rebuild(self) -> None:
        self.sup.maybe_refresh()
        self.rig.t += 10
        self.assertFalse(self.sup.maybe_refresh())
        self.assertEqual(self.rig.refreshes, 1)

    def test_a_new_file_triggers_a_rebuild(self) -> None:
        """Day la bai quan trong nhat: file moi ve thi len song ngay."""
        self.sup.maybe_refresh()
        self.them_file()
        self.rig.t += 6                       # qua mot vong ngo
        self.assertTrue(self.sup.maybe_refresh())
        self.assertEqual(self.rig.refreshes, 2)

    def test_it_does_not_look_more_often_than_asked(self) -> None:
        """Ngo thu muc la re, nhung khong re bang khong ngo."""
        self.sup.maybe_refresh()
        self.them_file()
        self.rig.t += 1                       # chua toi vong ngo
        self.assertFalse(self.sup.maybe_refresh())
        self.rig.t += 5
        self.assertTrue(self.sup.maybe_refresh())

    def test_a_changed_file_triggers_a_rebuild(self) -> None:
        import os
        self.sup.maybe_refresh()
        f = self.hop / "ngay-1.xml"
        f.write_text("<PSI> doi roi </PSI>", encoding="utf-8")
        os.utime(f, (9e8, 9e8))               # moc khac han
        self.rig.t += 6
        self.assertTrue(self.sup.maybe_refresh())

    def test_a_deleted_file_triggers_a_rebuild(self) -> None:
        self.sup.maybe_refresh()
        (self.hop / "ngay-1.xml").unlink()
        self.rig.t += 6
        self.assertTrue(self.sup.maybe_refresh())

    def test_the_periodic_net_still_catches_a_quiet_directory(self) -> None:
        """Cua so EIT troi theo thoi gian du khong co file moi nao."""
        self.sup.maybe_refresh()
        self.rig.t += 3601
        self.assertTrue(self.sup.maybe_refresh())

    def test_watching_nothing_falls_back_to_the_clock(self) -> None:
        sup = self.rig.supervisor(refresh=("vtcsi", "refresh"), refresh_every=3600.0)
        sup.maybe_refresh()
        self.rig.t += 10
        self.assertFalse(sup.maybe_refresh())
        self.rig.t += 3600
        self.assertTrue(sup.maybe_refresh())

    def test_a_missing_directory_does_not_crash(self) -> None:
        sup = self.rig.supervisor(refresh=("vtcsi", "refresh"),
                                  watch=(self.hop / "khong-co",))
        self.assertTrue(sup.maybe_refresh())
        self.rig.t += 6
        self.assertFalse(sup.maybe_refresh())

    def test_a_failed_rebuild_does_not_stop_the_broadcast(self) -> None:
        self.rig.refresh_code = 2
        self.sup.maybe_refresh()
        self.assertTrue(self.sup.start())
        self.assertEqual(len(self.rig.spawned), 1)


class TestRefresh(unittest.TestCase):
    def test_nothing_runs_when_no_command_is_given(self) -> None:
        rig = Rig()
        sup = rig.supervisor()
        sup.maybe_refresh()
        self.assertEqual(rig.refreshes, 0)

    def test_it_runs_once_at_startup(self) -> None:
        rig = Rig()
        sup = rig.supervisor(refresh=("vtcsi", "build"))
        self.assertTrue(sup.maybe_refresh())
        self.assertEqual(rig.refreshes, 1)

    def test_it_does_not_run_again_too_soon(self) -> None:
        rig = Rig()
        sup = rig.supervisor(refresh=("vtcsi", "build"), refresh_every=3600)
        sup.maybe_refresh()
        rig.t += 60
        self.assertFalse(sup.maybe_refresh())
        self.assertEqual(rig.refreshes, 1)

    def test_it_runs_again_when_due(self) -> None:
        rig = Rig()
        sup = rig.supervisor(refresh=("vtcsi", "build"), refresh_every=3600)
        sup.maybe_refresh()
        rig.t += 3601
        self.assertTrue(sup.maybe_refresh())
        self.assertEqual(rig.refreshes, 2)

    def test_a_failed_refresh_does_not_stop_the_broadcast(self) -> None:
        """Bang hom qua con hon khong co bang nao."""
        rig = Rig()
        rig.refresh_code = 2
        sup = rig.supervisor(refresh=("vtcsi", "build"))
        sup.maybe_refresh()
        self.assertTrue(sup.start())
        self.assertEqual(len(rig.spawned), 1)


if __name__ == "__main__":
    unittest.main()
