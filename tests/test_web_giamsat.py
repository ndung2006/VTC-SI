"""Màn giám sát — lưới lịch sẽ lên sóng.

Câu hỏi màn này trả lời là **đầu thu sẽ thấy gì**.

Một phép lọc: chỉ **TS actual** — ``eitinject --actual --ts-id N`` chỉ sinh EIT
cho một transport stream.

Kênh **tắt EPG** vẫn có dòng, nhưng dòng **rỗng**. Hai nửa của luật đó đều phải
đúng, và ``TestTurningEpgOffEmptiesTheRow`` giữ cả hai: bỏ nửa đầu thì màn giám
sát giấu mất kênh; bỏ nửa sau thì công tắc EPG thành lời hứa suông.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.config import loader
from vtcsi.epg.transform import timeline as T

NGUON = Path(__file__).parent.parent / "Bang mau" / "File xml đầu vào cho EPG.xml"
CO_LICH = "2026-09-08"


class GiamSatCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        if not NGUON.exists():
            raise unittest.SkipTest("khong co file lich mau")
        cls._seed = seed.committed_config()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(Path(self._seed.name) / "config", self.dir)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        shutil.copy(NGUON, self.inbox / "lich.xml")

        from vtcsi.web.app import create_app
        self.c = TestClient(
            create_app(self.dir, self.root, require_login=False,
                       build_dir=self.root / "build",
                       eit_dir=self.root / "build" / "eit", inbox=self.inbox),
            follow_redirects=False)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    def data(self, ngay: str = CO_LICH) -> dict:
        r = self.c.get(f"/giam-sat/du-lieu?ngay={ngay}")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def ids(self, ngay: str = CO_LICH) -> set[int]:
        return {r["id"] for r in self.data(ngay)["dong"]}

    def actual(self):
        return next(s for s in loader.load(self.dir).sdts if s.actual)

    def tat_epg(self, ids: set[int]) -> None:
        cfg = loader.load(self.dir)
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=tuple(
                replace(x, eit_pf=False, eit_schedule=False)
                if x.service_id in ids else x for x in s.services))
            if s.actual else s for s in cfg.sdts))
        loader.save(cfg, self.dir)

    def bat_het(self) -> None:
        cfg = loader.load(self.dir)
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=tuple(
                replace(x, eit_pf=True, eit_schedule=True) for x in s.services))
            for s in cfg.sdts))
        loader.save(cfg, self.dir)


class TestThePage(GiamSatCase):
    def test_it_opens(self) -> None:
        self.assertEqual(self.c.get("/giam-sat").status_code, 200)

    def test_it_names_the_transport_stream_it_covers(self) -> None:
        page = self.c.get("/giam-sat").text
        self.assertIn(f"TS {self.actual().ts_id}", page)
        self.assertIn("actual", page)

    def test_a_nonsense_date_falls_back_to_today_instead_of_crashing(self) -> None:
        r = self.c.get("/giam-sat/du-lieu?ngay=hom-qua")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ngay"], datetime.now(timezone.utc)
                         .astimezone(T.VN).date().isoformat())

    def test_no_date_means_today(self) -> None:
        d = self.c.get("/giam-sat/du-lieu").json()
        self.assertTrue(d["hom_nay"])

    def test_an_empty_inbox_is_explained_not_silent(self) -> None:
        """Luoi trong vi khong co du lieu KHAC voi cac kenh khong co chuong trinh."""
        (self.inbox / "lich.xml").unlink()
        d = self.data()
        self.assertIn("hop thu rong", d["canh_bao"])
        self.assertEqual(d["tong"]["su_kien"], 0)
        self.assertGreater(d["tong"]["kenh"], 0)
        self.assertIn("Quản lý PSI/SI:", self.c.get("/giam-sat").text)


class TestScope(GiamSatCase):
    def test_only_the_actual_transport_stream(self) -> None:
        """Kenh o TS khac khong he co bang EIT nao tu he nay."""
        cfg = loader.load(self.dir)
        khac = {x.service_id for s in cfg.sdts if not s.actual
                for x in s.services}
        self.assertTrue(khac, "ban gieo phai co TS other de thu")
        self.assertEqual(self.ids() & khac, set())

    def test_every_channel_of_the_actual_ts_is_listed(self) -> None:
        """Du ca kenh dang TAT — man giam sat la danh muc du cua TS."""
        tren = {x.service_id for x in self.actual().services}
        self.assertEqual(self.ids(), tren)

    def test_the_list_does_not_shrink_when_epg_is_turned_off(self) -> None:
        self.bat_het()
        truoc = self.ids()
        self.tat_epg(set(sorted(truoc)[:5]))
        self.assertEqual(self.ids(), truoc)

    def test_a_channel_with_no_programmes_still_gets_a_row(self) -> None:
        """Chinh nhung dong rong moi la thu dang nhin."""
        self.bat_het()
        d = self.data()
        self.assertGreater(d["tong"]["trong"], 0)
        self.assertEqual(d["tong"]["kenh"],
                         d["tong"]["co_lich"] + d["tong"]["trong"])

    def test_the_three_counters_always_add_up(self) -> None:
        """co_lich + trong + tat_epg = kenh, o moi trang thai cong tac."""
        self.bat_het()
        t = self.data()["tong"]
        self.assertEqual(t["kenh"], t["co_lich"] + t["trong"] + t["tat_epg"])
        self.tat_epg(set(sorted(self.ids())[:4]))
        t = self.data()["tong"]
        self.assertEqual(t["kenh"], t["co_lich"] + t["trong"] + t["tat_epg"])


class TestTurningEpgOffEmptiesTheRow(GiamSatCase):
    """Yeu cau chinh: kenh tat VAN CO DONG, nhung dong RONG."""

    def test_the_row_stays(self) -> None:
        self.bat_het()
        truoc = self.ids()
        self.tat_epg(set(sorted(truoc)[:3]))
        self.assertEqual(self.ids(), truoc)

    def test_the_row_says_it_is_off(self) -> None:
        self.bat_het()
        bo = sorted(self.ids())[0]
        self.tat_epg({bo})
        dong = {r["id"]: r for r in self.data()["dong"]}
        self.assertFalse(dong[bo]["epg"])
        self.assertTrue(all(r["epg"] for i, r in dong.items() if i != bo))

    def test_its_programmes_go_though_the_inbox_still_has_them(self) -> None:
        """Nua quan trong: hop thu VAN co lich, ma dong phai rong."""
        self.bat_het()
        co = next(r for r in self.data()["dong"] if r["muc"])
        self.tat_epg({co["id"]})
        sau = {r["id"]: r for r in self.data()["dong"]}
        self.assertEqual(sau[co["id"]]["muc"], [])
        self.assertEqual(sau[co["id"]]["ho"], [])

    def test_the_event_count_drops_by_exactly_that_channel(self) -> None:
        self.bat_het()
        d = self.data()
        co = next(r for r in d["dong"] if r["muc"])
        self.tat_epg({co["id"]})
        self.assertEqual(self.data()["tong"]["su_kien"],
                         d["tong"]["su_kien"] - len(co["muc"]))

    def test_the_others_are_untouched(self) -> None:
        self.bat_het()
        truoc = {r["id"]: len(r["muc"]) for r in self.data()["dong"]}
        bo = sorted(truoc)[0]
        self.tat_epg({bo})
        sau = {r["id"]: len(r["muc"]) for r in self.data()["dong"]}
        self.assertEqual(sau, {**truoc, bo: 0})

    def test_turning_it_back_on_brings_it_back(self) -> None:
        self.bat_het()
        truoc = self.ids()
        bo = set(sorted(truoc)[:2])
        self.tat_epg(bo)
        self.bat_het()
        self.assertEqual(self.ids(), truoc)

    def test_the_count_of_hidden_channels_is_reported(self) -> None:
        """An di ma khong noi la giau — nguoi ta se tuong kenh do mat lich."""
        self.bat_het()
        self.assertEqual(self.data()["tong"]["tat_epg"], 0)
        self.tat_epg(set(sorted(self.ids())[:4]))
        self.assertEqual(self.data()["tong"]["tat_epg"], 4)

    def test_the_page_says_so_too(self) -> None:
        self.bat_het()
        self.tat_epg(set(sorted(self.ids())[:2]))
        page = self.c.get("/giam-sat").text
        self.assertIn("2 kênh đang", page)
        self.assertIn("tắt EPG", page)

    def test_off_is_counted_apart_from_missing(self) -> None:
        """Rong vi TAT khac rong vi THIEU LICH — mot ben la lua chon."""
        self.bat_het()
        d = self.data()
        self.tat_epg({next(r["id"] for r in d["dong"] if r["muc"])})
        sau = self.data()
        self.assertEqual(sau["tong"]["tat_epg"], 1)
        self.assertEqual(sau["tong"]["trong"], d["tong"]["trong"])
        self.assertEqual(sau["tong"]["co_lich"], d["tong"]["co_lich"] - 1)

    def test_turning_everything_off_still_lists_every_channel(self) -> None:
        het = {x.service_id for x in self.actual().services}
        self.tat_epg(het)
        d = self.data()
        self.assertEqual({r["id"] for r in d["dong"]}, het)
        self.assertEqual(d["tong"]["tat_epg"], len(het))
        self.assertEqual(d["tong"]["su_kien"], 0)
        self.assertEqual(d["tong"]["trong"], 0)


class TestTheShapeOfTheData(GiamSatCase):
    def test_times_are_minutes_not_strings(self) -> None:
        """Giao dien dat o o `phut x px`; gui chuoi gio la bat no phan tich lai."""
        r = next(x for x in self.data()["dong"] if x["muc"])
        for m in r["muc"][:5]:
            with self.subTest(m=m["t"][:20]):
                self.assertIsInstance(m["s"], int)
                self.assertIsInstance(m["p"], int)
                self.assertGreaterEqual(m["p"], 1)

    def test_minutes_are_local_time(self) -> None:
        """Su kien 00:00 gio Viet Nam phai ra phut 0, khong phai 420."""
        r = next(x for x in self.data()["dong"] if x["muc"])
        dau = min(m["s"] for m in r["muc"])
        self.assertLess(dau, 60, "moc dau ngay bi lech — co the dang dung UTC")

    def test_gaps_come_as_pairs(self) -> None:
        d = self.data()
        co_ho = [r for r in d["dong"] if r["ho"]]
        self.assertTrue(co_ho, "ban mau phai co it nhat mot lo hong")
        for g in co_ho[0]["ho"]:
            self.assertEqual(len(g), 2)
            self.assertGreaterEqual(g[1], T.MIN_GAP)

    def test_the_summary_matches_the_rows(self) -> None:
        d = self.data()
        self.assertEqual(d["tong"]["kenh"], len(d["dong"]))
        self.assertEqual(d["tong"]["su_kien"],
                         sum(len(r["muc"]) for r in d["dong"]))
        self.assertEqual(d["tong"]["lo_hong"],
                         sum(len(r["ho"]) for r in d["dong"]))

    def test_a_day_with_no_schedule_is_all_empty_rows(self) -> None:
        d = self.data("2026-12-25")
        self.assertEqual(d["tong"]["su_kien"], 0)
        self.assertEqual(d["tong"]["trong"], d["tong"]["kenh"])

    def test_a_programme_from_the_night_before_starts_before_zero(self) -> None:
        hom_sau = (date.fromisoformat(CO_LICH) + timedelta(days=1)).isoformat()
        d = self.data(hom_sau)
        dau = [m["s"] for r in d["dong"] for m in r["muc"]]
        if dau:
            self.assertLessEqual(min(dau), 0)


if __name__ == "__main__":
    unittest.main()
