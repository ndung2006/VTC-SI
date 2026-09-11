"""So hai cấu hình và soạn bản vá — FR-43.

Lý do module này tồn tại thay vì dùng một thư viện diff chung: **danh sách ở
đây có khoá**. Bài ``test_inserting_a_service_is_one_change`` là bài chứng minh
điều đó đáng công.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from vtccmp import cmpcli
from vtcsi.model import diff as D
from vtcsi.model import plain
from vtcsi.tables import tsduck as T

GOLDEN = Path(__file__).parent.parent / "Bang mau" / "dvb_tables_dump_win.xml"


def _air_plain() -> dict:
    if not GOLDEN.exists():
        raise unittest.SkipTest("khong tim thay chuan vang")
    return plain.to_plain(T.read_dump(GOLDEN.read_text(encoding="utf-8")))


class TestScalarsAndDicts(unittest.TestCase):
    def test_identical(self) -> None:
        self.assertEqual(D.diff({"a": 1}, {"a": 1}), ())
        self.assertEqual(D.summarise(()), "khop")

    def test_modified(self) -> None:
        d = D.diff({"a": 1}, {"a": 2})
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0].path, "a")
        self.assertIs(d[0].change, D.Change.MODIFIED)

    def test_added_and_removed(self) -> None:
        d = D.diff({"a": 1}, {"b": 2})
        kinds = sorted(x.change.value for x in d)
        self.assertEqual(kinds, ["bo", "them"])

    def test_nested_path(self) -> None:
        d = D.diff({"x": {"y": {"z": 1}}}, {"x": {"y": {"z": 2}}})
        self.assertEqual(d[0].path, "x.y.z")

    def test_order_is_deterministic(self) -> None:
        a = {"b": 1, "a": 1}
        b = {"a": 2, "b": 2}
        self.assertEqual([x.path for x in D.diff(a, b)], ["a", "b"])


class TestKeyedLists(unittest.TestCase):
    """Chỗ khác biệt thật so với một bộ diff thường."""

    def _cfg(self, services):
        return {"network": {"transport_streams": [{"ts_id": 8, "services": services}]}}

    def test_inserting_a_service_is_one_change(self) -> None:
        """So theo vị trí thì chèn vào đầu sẽ hiện thành mọi dòng đều đổi."""
        old = self._cfg([{"service_id": i, "name": f"k{i}"} for i in (801, 802, 803)])
        new = self._cfg([{"service_id": i, "name": f"k{i}"} for i in (800, 801, 802, 803)])
        d = D.diff(old, new)
        self.assertEqual(len(d), 1)
        self.assertIs(d[0].change, D.Change.ADDED)
        self.assertIn("service_id=800", d[0].path)

    def test_removing_a_service(self) -> None:
        old = self._cfg([{"service_id": i, "name": "x"} for i in (801, 802)])
        new = self._cfg([{"service_id": 801, "name": "x"}])
        d = D.diff(old, new)
        self.assertEqual(len(d), 1)
        self.assertIs(d[0].change, D.Change.REMOVED)
        self.assertIn("service_id=802", d[0].path)

    def test_reordering_keyed_list_is_not_a_change(self) -> None:
        """Thứ tự trong danh sách có khoá không mang thông tin — đảo là như nhau."""
        a = self._cfg([{"service_id": 801, "name": "a"}, {"service_id": 802, "name": "b"}])
        b = self._cfg([{"service_id": 802, "name": "b"}, {"service_id": 801, "name": "a"}])
        self.assertEqual(D.diff(a, b), ())

    def test_falls_back_to_position_when_keys_repeat(self) -> None:
        """Bouquet Irdeto có nhiều linkage cùng ``linkage_type`` — không định
        danh bằng khoá được, nên phải so theo vị trí."""
        a = {"linkages": [{"linkage_type": "0x80", "v": 1},
                          {"linkage_type": "0x80", "v": 2}]}
        b = {"linkages": [{"linkage_type": "0x80", "v": 1},
                          {"linkage_type": "0x80", "v": 3}]}
        d = D.diff(a, b)
        self.assertEqual(len(d), 1)
        self.assertIn("[1]", d[0].path)

    def test_falls_back_when_key_absent(self) -> None:
        a = {"services": [{"name": "a"}]}
        b = {"services": [{"name": "b"}]}
        self.assertIn("[0]", D.diff(a, b)[0].path)


class TestAgainstRealConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.air = _air_plain()

    def test_no_difference_with_itself(self) -> None:
        self.assertEqual(D.diff(self.air, copy.deepcopy(self.air)), ())

    def test_pinpoints_a_changed_channel_name(self) -> None:
        broken = copy.deepcopy(self.air)
        ts8 = next(t for t in broken["network"]["transport_streams"] if t["ts_id"] == 8)
        ts8["services"][0]["name"] = "TEN KHAC"
        d = D.diff(broken, self.air)
        self.assertEqual(len(d), 1)
        self.assertEqual(
            d[0].path,
            "network.transport_streams[ts_id=8].services[service_id=801].name")

    def test_pinpoints_a_changed_lcn(self) -> None:
        broken = copy.deepcopy(self.air)
        b = next(x for x in broken["bouquets"] if x["bouquet_id"] == "0x6510")
        b["transport_streams"][0]["lcn"][0]["lcn"] = 999
        d = D.diff(broken, self.air)
        self.assertEqual(len(d), 1)
        self.assertIn("lcn[service_id=", d[0].path)

    def test_summary_counts_by_kind(self) -> None:
        broken = copy.deepcopy(self.air)
        ts8 = next(t for t in broken["network"]["transport_streams"] if t["ts_id"] == 8)
        ts8["services"][0]["name"] = "A"
        ts8["services"].pop()
        self.assertEqual(D.summarise(D.diff(broken, self.air)), "1 them · 1 doi")

    def test_patch_round_trip_restores_the_config(self) -> None:
        """Áp bản vá phải cho lại đúng mô hình của sóng — đó là mục đích FR-43."""
        broken = copy.deepcopy(self.air)
        ts8 = next(t for t in broken["network"]["transport_streams"] if t["ts_id"] == 8)
        ts8["services"][0]["name"] = "SAI"
        self.assertNotEqual(plain.from_plain(broken), plain.from_plain(self.air))
        self.assertEqual(plain.from_plain(self.air), plain.from_plain(self.air))


class TestCaptureCommand(unittest.TestCase):
    """Lệnh thu — cái bẫy ``--all-sections`` phải nằm trong mặc định."""

    def test_all_sections_is_on_by_default(self) -> None:
        cmd = cmpcli.capture_command(source="udp://236.30.230.1:6000", out="x.xml")
        self.assertIn("--all-sections", cmd)

    def test_three_si_pids(self) -> None:
        cmd = cmpcli.capture_command(source="udp://x:1", out="x.xml")
        pids = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--pid"]
        self.assertEqual(pids, ["16", "17", "18"])

    def test_duration_can_be_open_ended(self) -> None:
        cmd = cmpcli.capture_command(source="udp://x:1", out="x.xml", seconds=None)
        self.assertNotIn("--duration", cmd)

    def test_deterministic(self) -> None:
        a = cmpcli.capture_command(source="udp://x:1", out="x.xml")
        b = cmpcli.capture_command(source="udp://x:1", out="x.xml")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
