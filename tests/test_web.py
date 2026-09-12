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
import re
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.config import loader

#: Duoc dat trong `setUpClass` tu ban da commit — xem `tests/seed.py`.
GOC: Path
TS = 8
SID = 838  # dich vu co that trong ban gieo


class WebCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi — giao dien la phan tuy chon")
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


class TestTheRouteTableIsComplete(WebCase):
    """Kiem ke tuyen duong — bai nay ra doi vi mot lan suyt mat.

    Mot lan sua bang cach cat-va-dan da xoa nguyen khoi route bouquet, va thu
    duy nhat bat duoc la mot subtest o cho khac, bao "404 != 500". Ghim danh
    sach o day de lan sau lo mat thi bao thang vao mat.
    """

    MONG_DOI = {
        ("GET", "/"),
        ("GET", "/ts/{ts_id}"),
        ("GET", "/ts/{ts_id}/service/{service_id}"),
        ("GET", "/ts/{ts_id}/new"),
        ("POST", "/ts/{ts_id}/service/save"),
        ("POST", "/ts/{ts_id}/eit"),
        ("POST", "/ts/{ts_id}/service/{service_id}/delete"),
        ("POST", "/version/set"),
        ("POST", "/ap-dung"),
        ("GET", "/giam-sat"),
        ("GET", "/giam-sat/du-lieu"),
        ("GET", "/epg"),
        ("POST", "/api/epg"),
        ("POST", "/epg/tai-len"),
        ("POST", "/epg/xoa"),
        ("POST", "/epg/ve-moi"),
        ("GET", "/dau-ra"),
        ("POST", "/dau-ra/luu"),
        ("GET", "/bouquet/{raw}"),
        ("POST", "/bouquet/{raw}/ts/{ts_id}/lcn"),
        ("POST", "/bouquet/{raw}/ts/{ts_id}/add"),
        ("POST", "/bouquet/{raw}/ts/{ts_id}/remove"),
        ("POST", "/bouquet/{raw}/ts/add"),
        ("POST", "/bouquet/{raw}/ts/drop"),
        ("GET", "/linkage"),
        ("GET", "/linkage/{raw}/{index}"),
        ("POST", "/linkage/{raw}/save"),
        ("POST", "/linkage/{raw}/{index}/delete"),
        ("GET", "/thay-doi"),
        ("POST", "/thay-doi/commit"),
        ("GET", "/dang-nhap"),
        ("POST", "/dang-nhap"),
        ("POST", "/dang-xuat"),
        ("GET", "/quan-tri"),
        ("POST", "/quan-tri/doi-mat-khau"),
    }

    def _routes(self) -> set:
        out = set()
        for r in self.c.app.routes:
            for m in getattr(r, "methods", ()) or ():
                if m in ("GET", "POST"):
                    out.add((m, r.path))
        return out

    def test_nothing_is_missing(self) -> None:
        thieu = self.MONG_DOI - self._routes()
        self.assertEqual(thieu, set(), f"mat {len(thieu)} tuyen duong")

    def test_nothing_appeared_unannounced(self) -> None:
        """Them route ma quen ghi vao day thi bai nay nhac."""
        la = self._routes() - self.MONG_DOI
        self.assertEqual(la, set(), "co route moi chua ghi vao MONG_DOI")

    def test_the_old_bump_route_is_gone(self) -> None:
        """`/version/bump` da thanh `/version/set` — version nhap tay, lui duoc."""
        self.assertNotIn(("POST", "/version/bump"), self._routes())


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


class TestBrokenConfigIsNotAStackTrace(WebCase):
    """Cau hinh hong thi ra TRANG, khong ra stack trace Python.

    Giao dien doc lai YAML moi luot, nen chi mot file hong — thuong la sua tay
    roi lech thut dau dong — la moi trang chet. Nem stack trace vao mat nguoi
    truc luc hai gio sang khong giup duoc gi.
    """

    def setUp(self) -> None:
        super().setUp()
        import yaml
        from vtcsi.web.app import create_app
        f = self.dir / "bouquets" / "6604-quang-ninh.yaml"
        if not f.exists():
            self.skipTest("ban gieo khong co bouquet 0x6604")
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d["transport_streams"][0]["services"].append(9999)
        f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
        self.c = TestClient(create_app(self.dir, self.root, require_login=False),
                            raise_server_exceptions=False)

    def test_every_page_answers_with_a_readable_error(self) -> None:
        for url in ("/", f"/ts/{TS}", "/linkage", "/bouquet/6510"):
            with self.subTest(url=url):
                r = self.c.get(url)
                self.assertEqual(r.status_code, 500)
                self.assertIn("Cấu hình không đọc được", r.text)

    def test_it_names_what_is_wrong_and_where(self) -> None:
        text = self.c.get("/").text
        self.assertIn("9999", text)
        self.assertIn("0x6604", text)

    def test_it_offers_the_way_back(self) -> None:
        self.assertIn("git checkout -- config", self.c.get("/").text)

    def test_no_stack_trace_reaches_the_browser(self) -> None:
        text = self.c.get("/").text
        self.assertNotIn("Traceback", text)
        self.assertNotIn(".py\", line", text)

    def test_the_changes_page_still_works(self) -> None:
        """Day moi la diem quan trong: van xem duoc diff va quay lui duoc.

        Trang `thay-doi` khong nap cau hinh, nen no song sot qua mot file hong
        — va no dung la trang can dung de sua chuyen do.
        """
        self.assertEqual(self.c.get("/thay-doi").status_code, 200)


class TestTheEpgSwitch(WebCase):
    """Cột EPG trên trang TS — một công tắc cho mỗi kênh.

    Công tắc đặt **cả hai** cờ ``eit_pf`` và ``eit_schedule``, vì câu hỏi người
    vận hành đang trả lời là "kênh này có EPG hay không". Việc nó **thật sự**
    chặn EIT nằm ở ``test_cli_run.py`` — ở đây chỉ kiểm phần ghi cấu hình.
    """

    def flags(self):
        return {x.service_id: (x.eit_pf, x.eit_schedule) for x in self.sdt().services}

    def send(self, on: set[int]):
        return self.c.post(f"/ts/{TS}/eit",
                           data={f"eit_{s}": "true" for s in on},
                           follow_redirects=False)

    def all_ids(self) -> set[int]:
        return {x.service_id for x in self.sdt().services}

    def test_turning_one_channel_off(self) -> None:
        ids = self.all_ids()
        target = sorted(ids)[0]
        self.assertRedirectCarries(self.send(ids - {target}), "note", "tắt")
        self.assertEqual(self.flags()[target], (False, False))

    def test_the_others_are_untouched(self) -> None:
        ids = self.all_ids()
        target = sorted(ids)[0]
        before = self.flags()
        self.send(ids - {target})
        after = self.flags()
        self.assertEqual({k: v for k, v in before.items() if k != target},
                         {k: v for k, v in after.items() if k != target})

    def test_both_flags_move_together(self) -> None:
        ids = self.all_ids()
        target = sorted(ids)[0]
        self.send(ids - {target})
        self.assertEqual(self.flags()[target], (False, False))
        self.send(ids)
        self.assertEqual(self.flags()[target], (True, True))

    def test_turning_everything_off(self) -> None:
        self.assertRedirectCarries(self.send(set()), "note", "0 bật")
        self.assertTrue(all(v == (False, False) for v in self.flags().values()))

    def test_turning_everything_back_on(self) -> None:
        self.send(set())
        self.send(self.all_ids())
        self.assertTrue(all(v == (True, True) for v in self.flags().values()))

    def test_sending_no_change_is_refused_not_silently_accepted(self) -> None:
        """Bam ma khong doi gi thi nguoi ta dang nham — im lang se giau di."""
        self.assertRedirectCarries(self.send(self.all_ids()), "err", "không có kênh nào")

    def test_an_unknown_transport_stream_is_refused(self) -> None:
        r = self.c.post("/ts/999/eit", data={}, follow_redirects=False)
        self.assertRedirectCarries(r, "err", "999")

    def test_the_switch_shows_up_on_the_page(self) -> None:
        page = self.c.get(f"/ts/{TS}").text
        self.assertIn("cong-tac", page)
        self.assertIn("Lưu cột EPG", page)
        self.assertIn("Bật", page)

    def test_a_mismatched_pair_is_flagged_on_the_page(self) -> None:
        """p/f va lich khai khac nhau thi cot phai noi ra, khong lam tron."""
        from dataclasses import replace
        cfg = self.cfg()
        sdt = self.sdt()
        target = sorted(self.all_ids())[0]
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=tuple(
                replace(x, eit_pf=True, eit_schedule=False)
                if x.service_id == target else x for x in s.services))
            if s.ts_id == TS else s for s in cfg.sdts))
        loader.save(cfg, self.dir)
        self.assertIn("lệch", self.c.get(f"/ts/{TS}").text)


class TestEditingAService(WebCase):
    def test_rename_is_written_to_yaml(self) -> None:
        r = self.post(f"/ts/{TS}/service/save", service_id=SID, name="VTC THU NGHIEM",
                      provider="VTC", service_type=1, creating="false")
        self.assertRedirectCarries(r, "note", "sửa")
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        self.assertEqual(svc.name, "VTC THU NGHIEM")

    def test_blank_name_is_refused(self) -> None:
        r = self.post(f"/ts/{TS}/service/save", service_id=SID, name="   ",
                      provider="VTC", service_type=1, creating="false")
        self.assertRedirectCarries(r, "err", "tên dịch vụ")
        self.assertNotEqual(
            next(x for x in self.sdt().services if x.service_id == SID).name.strip(), "")

    def test_an_unset_switch_turns_epg_off_on_both_flags(self) -> None:
        """Cong tac khong bat thi CA HAI co ve false, khong phai mot."""
        self.post(f"/ts/{TS}/service/save", service_id=SID, name="X", provider="",
                  service_type=1, creating="false")  # khong gui `epg`
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        self.assertFalse(svc.eit_pf)
        self.assertFalse(svc.eit_schedule)

    def test_the_switch_sets_both_flags_together(self) -> None:
        self.post(f"/ts/{TS}/service/save", service_id=SID, name="X", provider="",
                  service_type=1, epg="true", creating="false")
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        self.assertTrue(svc.eit_pf)
        self.assertTrue(svc.eit_schedule)

    def test_a_hand_edited_mismatch_is_healed_on_save(self) -> None:
        """Hai co lech nhau chi den tu sua YAML tay; luu lai la dua ve mot moi."""
        from dataclasses import replace
        cfg = self.cfg()
        cfg = replace(cfg, sdts=tuple(
            replace(s, services=tuple(
                replace(x, eit_pf=True, eit_schedule=False)
                if x.service_id == SID else x for x in s.services))
            if s.ts_id == TS else s for s in cfg.sdts))
        loader.save(cfg, self.dir)

        self.post(f"/ts/{TS}/service/save", service_id=SID, name="X", provider="",
                  service_type=1, epg="true", creating="false")
        svc = next(x for x in self.sdt().services if x.service_id == SID)
        self.assertEqual(svc.eit_pf, svc.eit_schedule)

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
        self.assertRedirectCarries(self.add(4242, "KENH MOI"), "note", "thêm")
        self.assertTrue(self.in_sdt(4242))

    def test_duplicate_service_id_is_refused(self) -> None:
        self.add(4242, "KENH MOI")
        r = self.add(4242, "TRUNG SO")
        self.assertRedirectCarries(r, "err", "đã tồn tại")
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
        self.assertRedirectCarries(r, "err", "gõ đúng tên")
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


class TestSettingAVersion(WebCase):
    """Đặt version **bằng tay**, lùi lại được.

    Đầu thu phát hiện version *đổi* chứ không phải *tăng* — trường 5 bit quay
    vòng nên không có thứ tự tuyệt đối. Nếu chỉ cho tăng thì cách duy nhất để
    sửa một lần đặt nhầm là bấm thêm 31 lần, và mỗi lần đó cả mạng dò lại kênh.
    """

    def set(self, table: str, version: int, confirm: str | None = None):
        return self.post("/version/set", table=table, version=version,
                         confirm=str(version) if confirm is None else confirm)

    def nit(self) -> int:
        return self.cfg().network.version

    def test_a_normal_step_forward(self) -> None:
        now = self.nit()
        self.assertRedirectCarries(self.set("nit", (now + 1) % 32), "note",
                                   "bước kế tiếp")
        self.assertEqual(self.nit(), (now + 1) % 32)

    def test_a_step_back_is_allowed(self) -> None:
        """Day la ca ma ban cu chi cho tang khong lam duoc."""
        now = self.nit()
        self.set("nit", (now + 1) % 32)
        self.assertRedirectCarries(self.set("nit", now), "note", "lùi lại")
        self.assertEqual(self.nit(), now)

    def test_a_far_jump_is_allowed_but_named(self) -> None:
        self.assertRedirectCarries(self.set("nit", (self.nit() + 7) % 32),
                                   "note", "nhảy xa")

    def test_it_wraps_after_thirty_one(self) -> None:
        self.set("nit", 31)
        self.assertRedirectCarries(self.set("nit", 0), "note", "bước kế tiếp")
        self.assertEqual(self.nit(), 0)

    def test_the_wrong_confirmation_changes_nothing(self) -> None:
        now = self.nit()
        want = (now + 3) % 32
        self.assertRedirectCarries(self.set("nit", want, confirm=str(want + 1)),
                                   "err", str(want))
        self.assertEqual(self.nit(), now)

    def test_an_empty_confirmation_changes_nothing(self) -> None:
        now = self.nit()
        self.set("nit", (now + 1) % 32, confirm="")
        self.assertEqual(self.nit(), now)

    def test_a_value_outside_five_bits_is_refused(self) -> None:
        now = self.nit()
        for bad in (32, 33, -1, 255):
            with self.subTest(bad=bad):
                self.assertRedirectCarries(self.set("nit", bad), "err",
                                           "ngoài dải")
                self.assertEqual(self.nit(), now)

    def test_setting_the_value_it_already_has_is_refused(self) -> None:
        """Khong phai thao tac rong: nguoi bam dang nham, va im lang se giau di."""
        self.assertRedirectCarries(self.set("nit", self.nit()), "err", "rồi")

    def test_one_table_moves_and_the_others_do_not(self) -> None:
        before = {s.ts_id: s.version for s in self.cfg().sdts}
        self.set(f"sdt:{TS}", (before[TS] + 1) % 32)
        after = {s.ts_id: s.version for s in self.cfg().sdts}
        self.assertEqual(after[TS], (before[TS] + 1) % 32)
        self.assertEqual({k: v for k, v in before.items() if k != TS},
                         {k: v for k, v in after.items() if k != TS})

    def test_a_bouquet_version(self) -> None:
        b = self.cfg().bouquets[0]
        want = (b.version + 1) % 32
        self.assertRedirectCarries(
            self.set(f"bat:{b.bouquet_id:04x}", want), "note", "BAT")
        after = next(x for x in self.cfg().bouquets
                     if x.bouquet_id == b.bouquet_id)
        self.assertEqual(after.version, want)

    def test_an_unknown_table_is_refused(self) -> None:
        self.assertRedirectCarries(self.set("pat", 1), "err", "pat")

    def test_an_unknown_transport_stream_is_refused(self) -> None:
        self.assertRedirectCarries(self.set("sdt:999", 1), "err", "999")

    def test_saving_a_service_never_moves_a_version(self) -> None:
        """Sua noi dung va tuyen bo co thay doi la hai quyet dinh khac nhau."""
        before = (self.nit(), tuple(s.version for s in self.cfg().sdts))
        self.post(f"/ts/{TS}/service/save", service_id=4242, name="KENH MOI",
                  provider="VTC", service_type=1, creating="true")
        self.assertEqual(
            (self.nit(), tuple(s.version for s in self.cfg().sdts)), before)


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
        # Mot cong tac EPG, khong con hai o rieng — xem `entities.set_epg`.
        if svc.eit_pf or svc.eit_schedule:
            data["epg"] = "true"
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


class TestEveryInputTypeIsStyled(unittest.TestCase):
    """Mọi loại ô nhập chữ đều phải nằm trong luật CSS của ``base.html``.

    Thiếu một loại thì ô đó rơi về bề rộng mặc định của trình duyệt và lệch
    hẳn so với ô bên cạnh. Chuyện đã xảy ra thật: ``input[type=password]``
    bị bỏ quên, nên ở màn đăng nhập ô "Mật khẩu" ngắn hơn ô "Tên đăng nhập"
    — hai ô nằm ngay dưới nhau, và đó là màn hình đầu tiên người dùng thấy.

    Bài này không đọc CSS thật sự; nó chỉ so **danh sách loại đang dùng**
    với **danh sách loại được tạo kiểu**. Rẻ, và bắt đúng cái bẫy: thêm một
    loại ô mới vào một mẫu nào đó mà quên sờ tới bảng kiểu.
    """

    #: Loại không cần bề rộng — có luật riêng hoặc không hiện ra.
    MIEN = {"submit", "button", "hidden", "checkbox", "radio"}

    MAU = Path(__file__).parent.parent / "src" / "vtcsi" / "web" / "templates"

    def setUp(self) -> None:
        if not self.MAU.is_dir():
            self.skipTest("khong tim thay thu muc mau")
        self.base = (self.MAU / "base.html").read_text(encoding="utf-8")

    def dang_dung(self) -> set[str]:
        found: set[str] = set()
        for f in self.MAU.glob("*.html"):
            found |= set(re.findall(r'<input[^>]*\btype="([a-z]+)"',
                                    f.read_text(encoding="utf-8")))
        return found - self.MIEN

    def duoc_tao_kieu(self) -> set[str]:
        khoi = re.search(r"((?:input\[type=[a-z]+\],?\s*)+)[^{]*\{[^}]*width:100%",
                         self.base)
        self.assertIsNotNone(khoi, "khong tim thay luat be rong o base.html")
        return set(re.findall(r"input\[type=([a-z]+)\]", khoi.group(1)))

    def test_no_type_is_left_out(self) -> None:
        thieu = self.dang_dung() - self.duoc_tao_kieu()
        self.assertEqual(thieu, set(),
                         f"loai o nay dang dung ma chua duoc tao kieu: {thieu}")

    def test_password_is_in_there(self) -> None:
        """Ghim dung cai da tung quen."""
        self.assertIn("password", self.duoc_tao_kieu())

    def test_the_rule_is_not_stale(self) -> None:
        """Luat khong duoc liet ke loai da khong con dung o dau ca."""
        thua = self.duoc_tao_kieu() - self.dang_dung()
        self.assertEqual(thua, set(), f"luat con liet ke loai khong dung: {thua}")
