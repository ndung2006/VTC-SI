"""Màn hình bouquet và số kênh.

Tách khỏi ``test_web.py`` vì hình dạng biểu mẫu khác hẳn: bảng số kênh gửi lên
**nguyên khối**, tên trường sinh theo ``service_id``, nên mỗi bài phải dựng lại
cả biểu mẫu từ trạng thái hiện tại. Hàm ``form()`` làm đúng việc trình duyệt
làm, kể cả chỗ dễ quên nhất: **ô không tích thì không gửi gì cả**.

Luật số kênh đã có bài riêng ở ``test_lcn.py``. Ở đây chỉ kiểm rằng vỏ web
gọi đúng luật đó, và rằng một thao tác bị từ chối thì **không ghi gì xuống
đĩa** — đó mới là thứ mà lõi thuần không tự bảo đảm được.
"""

from __future__ import annotations

import filecmp
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.config import loader
from vtcsi.model import lcn as L

#: Duoc dat trong `setUpClass` tu ban da commit — xem `tests/seed.py`.
GOC: Path
BQ = 0x6510
HEX = f"{BQ:04x}"
TS = 8
NO_LCN = 877   # CAO BANG RADIO — kenh duy nhat trong 0x6510 khong co so
FIRST = 801    # dang giu so kenh 1


class BouquetCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        global GOC
        cls._seed = seed.committed_config()
        GOC = Path(cls._seed.name) / "config"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(GOC, self.dir)
        from vtcsi.web.app import create_app
        # `require_login=False`: cac bai o day kiem viec SUA CAU HINH, khong
        # kiem dang nhap. Bat dang nhap len se bat moi bai phai qua scrypt —
        # cham ~100 ms moi lan dung `setUp` — ma khong kiem them duoc gi.
        # Phan xac thuc co bo bai rieng o `test_web_auth.py`, va o day mac dinh
        # BAT la dieu bai `test_web_auth` ghim lai.
        self.c = TestClient(create_app(self.dir, self.root,
                                       require_login=False))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    def cfg(self):
        return loader.load(self.dir)

    def bouquet(self, bid: int = BQ):
        return next(x for x in self.cfg().bouquets if x.bouquet_id == bid)

    def loop(self, ts_id: int = TS, bid: int = BQ):
        return next(t for t in self.bouquet(bid).ts_loops if t.ts_id == ts_id)

    def number_of(self, service_id: int):
        return next((e.lcn for e in self.loop().lcn
                     if e.service_id == service_id), None)

    def visible_of(self, service_id: int):
        return next((e.visible for e in self.loop().lcn
                     if e.service_id == service_id), None)

    def form(self, override: dict[str, str] | None = None,
             hide: tuple[int, ...] = ()) -> dict[str, str]:
        """Dung lai bieu mau y het trinh duyet gui len.

        Diem tinh te: checkbox khong tich thi KHONG co trong form data. Nhieu
        loi giao dien sinh ra tu cho nay.
        """
        t = self.loop()
        data: dict[str, str] = {}
        for r in t.services:
            e = next((x for x in t.lcn if x.service_id == r.service_id), None)
            data[f"lcn_{r.service_id}"] = str(e.lcn) if e else ""
            if (e is None or e.visible) and r.service_id not in hide:
                data[f"vis_{r.service_id}"] = "true"
        data.update(override or {})
        return data

    def post(self, url: str, data: dict):
        return self.c.post(url, data=data, follow_redirects=False)

    def numbers(self, data: dict):
        return self.post(f"/bouquet/{HEX}/ts/{TS}/lcn", data)

    def kind(self, response) -> str:
        q = parse_qs(urlparse(response.headers.get("location", "")).query)
        return "note" if "note" in q else ("err" if "err" in q else "?")

    def said(self, response) -> str:
        q = parse_qs(urlparse(response.headers.get("location", "")).query)
        return (q.get("note") or q.get("err") or [""])[0]

    def assertRefused(self, response, fragment: str = "") -> None:
        self.assertEqual(self.kind(response), "err",
                         f"dang le phai tu choi, nhung: {self.said(response)}")
        if fragment:
            self.assertIn(fragment, self.said(response))

    def assertAccepted(self, response) -> None:
        self.assertEqual(self.kind(response), "note", self.said(response))

    def assertNothingWritten(self) -> None:
        """Thao tac bi tu choi khong duoc cham vao dia."""
        def walk(cmp_, prefix=""):
            out = [prefix + f for f in cmp_.diff_files]
            for name, sub in cmp_.subdirs.items():
                out += walk(sub, prefix + name + "/")
            return out
        self.assertEqual(walk(filecmp.dircmp(str(GOC), str(self.dir))), [])


class TestBouquetPagesRender(BouquetCase):
    def test_every_bouquet_opens(self) -> None:
        for b in self.cfg().bouquets:
            with self.subTest(bouquet=f"{b.bouquet_id:04x}"):
                r = self.c.get(f"/bouquet/{b.bouquet_id:04x}")
                self.assertEqual(r.status_code, 200)

    def test_an_unknown_bouquet_redirects(self) -> None:
        r = self.c.get("/bouquet/9999", follow_redirects=False)
        self.assertRefused(r, "9999")

    def test_nonsense_in_the_url_does_not_crash(self) -> None:
        r = self.c.get("/bouquet/zzzz", follow_redirects=False)
        self.assertRefused(r)

    def test_the_empty_bouquet_says_so(self) -> None:
        """RO-15 — 0x6520 phat mot bang BAT rong ra song."""
        self.assertIn("RO-15", self.c.get("/bouquet/6520").text)

    def test_a_grouping_bouquet_is_not_nagged_about_numbers(self) -> None:
        """0x6550 gom 48 kenh de khoa ma — khong phai danh sach kenh."""
        page = self.c.get("/bouquet/6550").text
        self.assertIn("không đánh số kênh nào", page)
        self.assertNotIn("khong co so kenh", page)

    def test_the_home_page_surfaces_the_audit(self) -> None:
        self.assertIn(str(NO_LCN), self.c.get("/").text)


class TestSettingNumbers(BouquetCase):
    def test_the_seeded_gap_can_be_filled(self) -> None:
        """Bai nay la ca ly do viet man hinh nay: 877 thieu so 416."""
        self.assertIsNone(self.number_of(NO_LCN))
        self.assertAccepted(self.numbers(self.form({f"lcn_{NO_LCN}": "416"})))
        self.assertEqual(self.number_of(NO_LCN), 416)
        self.assertEqual(L.check(self.cfg()), ())

    def test_a_duplicate_is_refused_and_nothing_is_written(self) -> None:
        r = self.numbers(self.form({f"lcn_{NO_LCN}": "1"}))
        self.assertRefused(r, "số kênh 1")
        self.assertNothingWritten()

    def test_out_of_range_is_refused(self) -> None:
        for bad in ("0", "1024", "2000", "-5"):
            with self.subTest(n=bad):
                self.assertRefused(self.numbers(self.form({f"lcn_{NO_LCN}": bad})))
                self.assertNothingWritten()

    def test_text_in_a_number_box_is_refused_by_name(self) -> None:
        r = self.numbers(self.form({f"lcn_{NO_LCN}": "muoi"}))
        self.assertRefused(r, str(NO_LCN))
        self.assertRefused(r, "muoi")

    def test_clearing_a_box_drops_that_number(self) -> None:
        self.assertIsNotNone(self.number_of(FIRST))
        self.assertAccepted(self.numbers(self.form({f"lcn_{FIRST}": ""})))
        self.assertIsNone(self.number_of(FIRST))

    def test_clearing_a_box_keeps_the_service_in_the_bouquet(self) -> None:
        """Bo so kenh khac voi bo khoi goi — day la hai nut khac nhau."""
        self.numbers(self.form({f"lcn_{FIRST}": ""}))
        self.assertIn(FIRST, {r.service_id for r in self.loop().services})

    def test_swapping_two_numbers_in_one_go(self) -> None:
        """Doi cho hai kenh phai lam duoc trong MOT luot.

        Neu bieu mau gui tung o thi buoc trung gian luon trung so, va thao tac
        binh thuong nay thanh khong the. Do la ly do gui nguyen bang.
        """
        a, b = FIRST, 802
        na, nb = self.number_of(a), self.number_of(b)
        self.assertIsNotNone(na)
        self.assertIsNotNone(nb)
        self.assertAccepted(self.numbers(
            self.form({f"lcn_{a}": str(nb), f"lcn_{b}": str(na)})))
        self.assertEqual((self.number_of(a), self.number_of(b)), (nb, na))

    def test_an_unrelated_transport_stream_is_untouched(self) -> None:
        before = {e.service_id: e.lcn for e in self.loop(3).lcn}
        self.numbers(self.form({f"lcn_{NO_LCN}": "416"}))
        self.assertEqual({e.service_id: e.lcn for e in self.loop(3).lcn}, before)

    def test_clash_with_another_transport_stream_is_refused(self) -> None:
        taken = self.loop(3).lcn[0].lcn
        self.assertRefused(self.numbers(self.form({f"lcn_{NO_LCN}": str(taken)})),
                           "TS 3")


class TestVisibility(BouquetCase):
    def test_unticking_hides_one_channel_only(self) -> None:
        self.assertTrue(self.visible_of(FIRST))
        self.assertAccepted(self.numbers(self.form(hide=(FIRST,))))
        self.assertFalse(self.visible_of(FIRST))
        others = [e.visible for e in self.loop().lcn if e.service_id != FIRST]
        self.assertTrue(all(others), "an mot kenh ma an luon ca danh sach")

    def test_ticking_again_shows_it(self) -> None:
        self.numbers(self.form(hide=(FIRST,)))
        # `form()` dung lai dung nhung gi trinh duyet gui, ma o da an thi hien
        # ra khong tich — nen phai tich lai tuong minh, y het nguoi dung.
        self.assertAccepted(self.numbers(self.form({f"vis_{FIRST}": "true"})))
        self.assertTrue(self.visible_of(FIRST))

    def test_hiding_keeps_the_number(self) -> None:
        n = self.number_of(FIRST)
        self.numbers(self.form(hide=(FIRST,)))
        self.assertEqual(self.number_of(FIRST), n)


class TestMembership(BouquetCase):
    def add(self, service_id: int, number: str = ""):
        return self.post(f"/bouquet/{HEX}/ts/{TS}/add",
                         {"service_id": service_id, "number": number})

    def remove(self, service_id: int):
        return self.post(f"/bouquet/{HEX}/ts/{TS}/remove",
                         {"service_id": service_id})

    def test_removing_takes_the_number_with_it(self) -> None:
        self.assertAccepted(self.remove(FIRST))
        self.assertNotIn(FIRST, {r.service_id for r in self.loop().services})
        self.assertIsNone(self.number_of(FIRST))
        self.assertEqual(L.blocking(L.check(self.cfg())), ())

    def test_removing_leaves_the_service_in_the_sdt(self) -> None:
        """Bo khoi goi khong phai la xoa kenh — kenh van phat."""
        self.remove(FIRST)
        sdt = next(s for s in self.cfg().sdts if s.ts_id == TS)
        self.assertIn(FIRST, {x.service_id for x in sdt.services})

    def test_removing_someone_absent_is_refused(self) -> None:
        self.assertRefused(self.remove(60000))
        self.assertNothingWritten()

    def test_add_then_remove_returns_to_the_start(self) -> None:
        self.remove(FIRST)
        self.assertAccepted(self.add(FIRST, "1"))
        self.assertEqual(self.number_of(FIRST), 1)
        self.assertEqual(L.check(self.cfg()), L.check(loader.load(GOC)))

    def test_adding_without_a_number_leaves_it_unnumbered(self) -> None:
        self.remove(FIRST)
        self.assertAccepted(self.add(FIRST))
        self.assertIn(FIRST, {r.service_id for r in self.loop().services})
        self.assertIsNone(self.number_of(FIRST))

    def test_adding_someone_already_there_is_refused(self) -> None:
        self.assertRefused(self.add(FIRST, "999"), "đã có")
        self.assertNothingWritten()

    def test_adding_with_a_taken_number_is_refused_and_writes_nothing(self) -> None:
        """Phai huy CA thao tac, khong duoc them roi bo so kenh."""
        self.remove(NO_LCN)
        before = {r.service_id for r in self.loop().services}
        self.assertRefused(self.add(NO_LCN, "1"))
        self.assertEqual({r.service_id for r in self.loop().services}, before)

    def test_adding_a_service_that_is_not_in_the_transport_stream(self) -> None:
        self.assertRefused(self.add(60000, "500"), "60000")
        self.assertNothingWritten()

    def test_a_number_that_is_not_a_number(self) -> None:
        self.remove(FIRST)
        self.assertRefused(self.add(FIRST, "mot"), "mot")


class TestDeletingAServiceClearsBouquets(BouquetCase):
    """Xoa han mot kenh phai gỡ no khoi MOI goi, ca so kenh lan tu cach."""

    def test_deleting_a_numbered_service(self) -> None:
        sdt = next(s for s in self.cfg().sdts if s.ts_id == TS)
        name = next(x.name for x in sdt.services if x.service_id == FIRST)
        r = self.post(f"/ts/{TS}/service/{FIRST}/delete", {"confirm_name": name})
        self.assertAccepted(r)

        after = self.cfg()
        self.assertFalse(any(e.service_id == FIRST
                             for b in after.bouquets for t in b.ts_loops
                             for e in t.lcn))
        self.assertFalse(any(r_.service_id == FIRST
                             for b in after.bouquets for t in b.ts_loops
                             for r_ in t.services))
        self.assertEqual(L.blocking(L.check(after)), ())


if __name__ == "__main__":
    unittest.main()
