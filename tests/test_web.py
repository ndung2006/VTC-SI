"""Giao diện nhập liệu — FR-34…41.

Mỗi bài chạy trên **bản sao** của ``config/`` trong thư mục tạm. Giao diện ghi
thật vào file, nên không có cách nào thử nó mà không ghi gì; thứ ta kiểm soát
được là ghi vào đâu.

Ba nhóm đáng chú ý hơn phần còn lại:

* ``TestNitFollowsSdt`` — thêm hay xoá dịch vụ phải kéo theo ``service_list``
  trong NIT. Đây là FR-3, và là đúng lỗi đã làm 26 kênh không hiện sau khi dò.
* ``TestDangerousThingsAreHard`` — tăng version và xoá kênh phải khó gõ nhầm.
* ``TestSavingChangesNothingElse`` — lưu lại nguyên trạng không được xáo file.
  Không có tính chất này thì ``git diff`` đầy nhiễu, và người ta sẽ ngừng đọc nó
  — lúc đó cơ chế đồng bộ của cả hệ thống mất tác dụng.

Bỏ qua khi chưa cài FastAPI: giao diện là phần tuỳ chọn, lõi không phụ thuộc nó.
"""

from __future__ import annotations

import filecmp
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

from vtcsi.config import loader

GOC = Path(__file__).parent.parent / "config"
TS = 8
SID = 838  # dich vu co that trong ban gieo


class WebCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi — giao dien la phan tuy chon")
        if not (GOC / "network.yaml").exists():
            raise unittest.SkipTest("chua gieo cau hinh")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(GOC, self.dir)

        from vtcsi.web.app import create_app
        self.c = TestClient(create_app(self.dir, self.root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    def cfg(self):
        return loader.load(self.dir)

    def sdt(self, ts_id: int = TS):
        return next(s for s in self.cfg().sdts if s.ts_id == ts_id)

    def in_sdt(self, service_id: int, ts_id: int = TS) -> bool:
        return any(x.service_id == service_id for x in self.sdt(ts_id).services)

    def in_nit(self, service_id: int, ts_id: int = TS) -> bool:
        loop = next(t for t in self.cfg().network.ts_loops if t.ts_id == ts_id)
        return any(r.service_id == service_id for r in loop.services)

    def post(self, url: str, **data):
        return self.c.post(url, data=data, follow_redirects=False)

    def add(self, service_id: int, name: str, **extra):
        data = dict(service_id=service_id, name=name, provider="VTC",
                    service_type=1, creating="true")
        data.update(extra)
        return self.post(f"/ts/{TS}/service/save", **data)

    def assertRedirectCarries(self, response, key: str, fragment: str) -> None:
        """Chuyen huong 303 co mang theo thong bao dung loai khong."""
        self.assertEqual(response.status_code, 303)
        where = response.headers.get("location", "")
        self.assertIn(f"{key}=", where, f"khong co {key} trong: {where}")
        from urllib.parse import parse_qs, urlparse
        got = parse_qs(urlparse(where).query).get(key, [""])[0]
        self.assertIn(fragment, got)


class TestEveryPageRenders(WebCase):
    """Truoc moi thu: cac trang co dung duoc khong."""

    def test_pages_answer_200(self) -> None:
        for url in ("/", f"/ts/{TS}", f"/ts/{TS}/service/{SID}",
                    f"/ts/{TS}/new", "/thay-doi"):
            with self.subTest(url=url):
                self.assertEqual(self.c.get(url).status_code, 200)

    def test_unknown_ts_redirects_instead_of_crashing(self) -> None:
        r = self.c.get("/ts/9999", follow_redirects=False)
        self.assertRedirectCarries(r, "err", "9999")

    def test_unknown_service_redirects(self) -> None:
        r = self.c.get(f"/ts/{TS}/service/65000", follow_redirects=False)
        self.assertRedirectCarries(r, "err", "65000")

    def test_notice_reaches_the_page(self) -> None:
        self.assertIn("da sua dich vu 838",
                      self.c.get(f"/ts/{TS}?note=da+sua+dich+vu+838").text)

    def test_empty_bouquet_is_flagged(self) -> None:
        """RO-15 — 0x6520 phat ra song mà khong co dich vu nao."""
        self.assertIn("rỗng", self.c.get("/").text)

    def test_missing_git_repo_is_stated_not_hidden(self) -> None:
        self.assertIn("chưa phải kho git", self.c.get("/").text)


class TestEditingAService(WebCase):
    def test_rename_is_written_to_yaml(self) -> None:
        r = self.post(f"/ts/{TS}/service/save", service_id=SID, name="VTC THU NGHIEM",
                      provider="VTC", service_type=1, creating="false")
        self.assertRedirectCarries(r, "note", "sua")
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        self.assertEqual(svc.name, "VTC THU NGHIEM")

    def test_blank_name_is_refused(self) -> None:
        r = self.post(f"/ts/{TS}/service/save", service_id=SID, name="   ",
                      provider="VTC", service_type=1, creating="false")
        self.assertRedirectCarries(r, "err", "ten dich vu")
        self.assertNotEqual(
            next(x for x in self.sdt().services if x.service_id == SID).name.strip(), "")

    def test_unchecked_box_clears_the_flag(self) -> None:
        """O khong tich phai thanh false — khong phai giu nguyen gia tri cu."""
        self.post(f"/ts/{TS}/service/save", service_id=SID, name="X", provider="",
                  service_type=1, creating="false")  # khong gui eit_pf
        self.assertFalse(next(x for x in self.sdt().services
                              if x.service_id == SID).eit_pf)

    def test_editing_one_service_leaves_the_rest_alone(self) -> None:
        before = {x.service_id: x.name for x in self.sdt().services}
        self.post(f"/ts/{TS}/service/save", service_id=SID, name="DOI TEN",
                  provider="VTC", service_type=1, creating="false")
        after = {x.service_id: x.name for x in self.sdt().services}
        self.assertEqual(set(before), set(after))
        self.assertEqual({k: v for k, v in before.items() if k != SID},
                         {k: v for k, v in after.items() if k != SID})


class TestAddingAService(WebCase):
    def test_new_service_lands_in_yaml(self) -> None:
        self.assertRedirectCarries(self.add(4242, "KENH MOI"), "note", "them")
        self.assertTrue(self.in_sdt(4242))

    def test_duplicate_service_id_is_refused(self) -> None:
        self.add(4242, "KENH MOI")
        r = self.add(4242, "TRUNG SO")
        self.assertRedirectCarries(r, "err", "da ton tai")
        self.assertEqual(
            next(x for x in self.sdt().services if x.service_id == 4242).name,
            "KENH MOI")

    def test_services_stay_sorted(self) -> None:
        """Thu tu tat dinh — neu khong thi `git diff` xao tung len."""
        self.add(500, "GIUA DANH SACH")
        ids = [x.service_id for x in self.sdt().services]
        self.assertEqual(ids, sorted(ids))


class TestNitFollowsSdt(WebCase):
    """FR-3 — day la bai quan trong nhat cua ca file.

    NIT khong biet ve mot dich vu thi dau thu khong luu no sau khi do, du SDT
    co khai day du. Barrowa mat 26 kenh vi dung buoc nay.
    """

    def test_adding_a_service_adds_it_to_the_nit(self) -> None:
        self.add(4242, "KENH MOI")
        self.assertTrue(self.in_nit(4242), "them vao SDT ma NIT khong biet")

    def test_deleting_a_service_removes_it_from_the_nit(self) -> None:
        self.add(4242, "KENH MOI")
        self.post(f"/ts/{TS}/service/4242/delete", confirm_name="KENH MOI")
        self.assertFalse(self.in_sdt(4242))
        self.assertFalse(self.in_nit(4242), "xoa khoi SDT ma NIT con tro toi")

    def test_service_type_reaches_the_nit_entry(self) -> None:
        self.add(4243, "PHAT THANH MOI", service_type=2)
        loop = next(t for t in self.cfg().network.ts_loops if t.ts_id == TS)
        ref = next(r for r in loop.services if r.service_id == 4243)
        self.assertEqual(ref.service_type, 2)

    def test_nit_matches_sdt_for_every_ts_after_any_edit(self) -> None:
        self.add(4242, "KENH MOI")
        cfg = self.cfg()
        by_ts = {s.ts_id: {x.service_id for x in s.services} for s in cfg.sdts}
        for loop in cfg.network.ts_loops:
            if loop.ts_id in by_ts:
                with self.subTest(ts=loop.ts_id):
                    self.assertEqual({r.service_id for r in loop.services},
                                     by_ts[loop.ts_id])


class TestDeletingAService(WebCase):
    def test_wrong_confirmation_keeps_the_service(self) -> None:
        r = self.post(f"/ts/{TS}/service/{SID}/delete", confirm_name="gõ đại")
        self.assertRedirectCarries(r, "err", "go dung ten")
        self.assertTrue(self.in_sdt(SID))

    def test_empty_confirmation_keeps_the_service(self) -> None:
        self.post(f"/ts/{TS}/service/{SID}/delete", confirm_name="")
        self.assertTrue(self.in_sdt(SID))

    def test_deletion_also_clears_bouquets(self) -> None:
        """Bo sot o BAT thi `from_plain` tu choi ca cau hinh — mat luon buoi phat."""
        cfg = self.cfg()
        target = next(
            (x.service_id for x in self.sdt().services
             if any(e.service_id == x.service_id
                    for b in cfg.bouquets for t in b.ts_loops
                    if t.ts_id == TS for e in t.lcn)), None)
        self.assertIsNotNone(target, "ban gieo phai co it nhat mot LCN o TS 8")
        name = next(x.name for x in self.sdt().services if x.service_id == target)

        self.post(f"/ts/{TS}/service/{target}/delete", confirm_name=name)
        after = self.cfg()
        self.assertFalse(any(e.service_id == target
                             for b in after.bouquets for t in b.ts_loops
                             for e in t.lcn), "con mot muc LCN tro toi kenh da xoa")
        self.assertFalse(any(r.service_id == target
                             for b in after.bouquets for t in b.ts_loops
                             for r in t.services))


class TestDangerousThingsAreHard(WebCase):
    def test_version_does_not_move_without_the_word(self) -> None:
        before = self.cfg().network.version
        r = self.post("/version/bump", table="nit", confirm="")
        self.assertRedirectCarries(r, "err", "TANG")
        self.assertEqual(self.cfg().network.version, before)

    def test_version_does_not_move_on_a_near_miss(self) -> None:
        before = self.cfg().network.version
        for typo in ("tang", "TANG ", "TĂNG", "yes"):
            with self.subTest(typo=typo):
                self.post("/version/bump", table="nit", confirm=typo)
                self.assertEqual(self.cfg().network.version, before)

    def test_confirmed_bump_moves_exactly_one(self) -> None:
        before = self.cfg().network.version
        self.post("/version/bump", table="nit", confirm="TANG")
        self.assertEqual(self.cfg().network.version, (before + 1) % 32)

    def test_bumping_one_sdt_leaves_the_others(self) -> None:
        before = {s.ts_id: s.version for s in self.cfg().sdts}
        self.post("/version/bump", table=f"sdt:{TS}", confirm="TANG")
        after = {s.ts_id: s.version for s in self.cfg().sdts}
        self.assertEqual(after[TS], (before[TS] + 1) % 32)
        self.assertEqual({k: v for k, v in before.items() if k != TS},
                         {k: v for k, v in after.items() if k != TS})

    def test_bumping_a_bouquet(self) -> None:
        b = self.cfg().bouquets[0]
        self.post("/version/bump", table=f"bat:{b.bouquet_id:04x}", confirm="TANG")
        after = next(x for x in self.cfg().bouquets if x.bouquet_id == b.bouquet_id)
        self.assertEqual(after.version, (b.version + 1) % 32)

    def test_unknown_table_is_refused(self) -> None:
        r = self.post("/version/bump", table="pat", confirm="TANG")
        self.assertRedirectCarries(r, "err", "pat")

    def test_saving_a_service_never_touches_a_version(self) -> None:
        """Sua noi dung va tang version la hai quyet dinh khac nhau."""
        before = (self.cfg().network.version,
                  tuple(s.version for s in self.cfg().sdts))
        self.add(4242, "KENH MOI")
        self.assertEqual((self.cfg().network.version,
                          tuple(s.version for s in self.cfg().sdts)), before)


class TestSavingChangesNothingElse(WebCase):
    """Ghi lai nguyen trang khong duoc lam xao file — neu khong, `git diff` vo dung."""

    def _differing_files(self) -> list[str]:
        def walk(cmp_, prefix=""):
            out = [prefix + f for f in cmp_.diff_files]
            for name, sub in cmp_.subdirs.items():
                out += walk(sub, prefix + name + "/")
            return out
        return walk(filecmp.dircmp(str(GOC), str(self.dir)))

    def test_copy_starts_identical(self) -> None:
        self.assertEqual(self._differing_files(), [])

    def test_resaving_a_service_unchanged_rewrites_nothing(self) -> None:
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        data = dict(service_id=svc.service_id, name=svc.name, provider=svc.provider,
                    service_type=int(svc.service_type), creating="false")
        if svc.eit_pf:
            data["eit_pf"] = "true"
        if svc.eit_schedule:
            data["eit_schedule"] = "true"
        if svc.free_ca_mode:
            data["free_ca_mode"] = "true"
        self.post(f"/ts/{TS}/service/save", **data)
        self.assertEqual(self._differing_files(), [],
                         "luu lai y nguyen ma file van doi")

    def test_one_edit_touches_one_ts_file(self) -> None:
        self.post(f"/ts/{TS}/service/save", service_id=SID, name="DOI TEN",
                  provider="VTC", service_type=1, creating="false")
        self.assertEqual(sorted(self._differing_files()),
                         [f"services/ts{TS}.yaml"])


if __name__ == "__main__":
    unittest.main()
