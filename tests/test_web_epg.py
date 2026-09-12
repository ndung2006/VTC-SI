"""Hộp thư lịch và tuyến nhận XML từ hệ lập lịch bên ngoài.

Đây là ranh giới giữa hệ này và một hệ không do ta kiểm soát, nên phần lớn bài
ở đây nói về **những gì bên kia gửi sai**: file hỏng, tên file lạ, vé sai, thân
rỗng. Một ranh giới chỉ đáng tin khi nó từ chối tốt.

Bài quan trọng nhất là ``TestNothingBadReachesTheInbox``: một file hỏng nằm
trong hộp thư sẽ làm hỏng lần sinh EIT kế tiếp, mà lần đó xảy ra **vài giây
sau** và không ai đang nhìn. Kiểm trước khi ghi là cách duy nhất để chuyện đó
không bao giờ xảy ra.
"""

from __future__ import annotations

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
from vtcsi.web import auth as A

NGUON = Path(__file__).parent.parent / "Bang mau" / "File xml đầu vào cho EPG.xml"
NGUOI = "admin"
MAT_KHAU = "mot cau dai de nho 2026"


class EpgCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        if not NGUON.exists():
            raise unittest.SkipTest("khong co file lich mau")
        cls.xml = NGUON.read_bytes()
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
        self.build = self.root / "build"
        self.auth_file = self.root / ".vtcsi-auth.json"
        A.save(self.auth_file, A.make(NGUOI, MAT_KHAU))
        self.ve = A.load(self.auth_file).token

        from vtcsi.web.app import create_app
        self.c = TestClient(
            create_app(self.dir, self.root, auth_file=self.auth_file,
                       build_dir=self.build, eit_dir=self.build / "eit",
                       inbox=self.inbox),
            follow_redirects=False)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    @property
    def head(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.ve}"}

    def gui(self, body: bytes | None = None, ten: str = "", **kw):
        url = f"/api/epg?ten={ten}" if ten else "/api/epg"
        return self.c.post(url, content=self.xml if body is None else body,
                           headers=self.head, **kw)

    def trong_hop(self) -> list[str]:
        if not self.inbox.is_dir():
            return []
        return sorted(p.name for p in self.inbox.iterdir())

    def dang_nhap(self) -> None:
        r = self.c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertEqual(r.status_code, 303)
        self.c.cookies.update(r.cookies)

    def said(self, r) -> str:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or q.get("err") or [""])[0]


class TestTheTicket(EpgCase):
    """Ve cho MAY: he lap lich khong go mat khau vao o dang nhap duoc."""

    def test_no_ticket_is_refused(self) -> None:
        self.assertEqual(self.c.post("/api/epg", content=self.xml).status_code, 401)

    def test_a_wrong_ticket_is_refused(self) -> None:
        r = self.c.post("/api/epg", content=self.xml,
                        headers={"Authorization": "Bearer bay gio moi biet"})
        self.assertEqual(r.status_code, 401)

    def test_a_session_cookie_is_not_a_ticket(self) -> None:
        """Hai loai xac thuc, hai duong rieng — khong nham lan duoc."""
        self.dang_nhap()
        self.assertEqual(self.c.post("/api/epg", content=self.xml).status_code, 401)

    def test_the_ticket_is_never_read_from_the_url(self) -> None:
        """URL nam trong log cua moi proxy; mot ve da vao log la mot ve da lo."""
        r = self.c.post(f"/api/epg?token={self.ve}", content=self.xml)
        self.assertEqual(r.status_code, 401)

    def test_both_header_spellings_work(self) -> None:
        for head in ({"Authorization": f"Bearer {self.ve}"},
                     {"X-VTCSI-Token": self.ve}):
            with self.subTest(head=list(head)[0]):
                r = self.c.post("/api/epg", content=self.xml, headers=head)
                self.assertEqual(r.status_code, 200)

    def test_bearer_is_case_insensitive(self) -> None:
        r = self.c.post("/api/epg", content=self.xml,
                        headers={"Authorization": f"bearer {self.ve}"})
        self.assertEqual(r.status_code, 200)

    def test_a_refusal_never_writes_anything(self) -> None:
        self.c.post("/api/epg", content=self.xml)
        self.assertEqual(self.trong_hop(), [])

    def test_changing_the_password_does_not_break_the_outside_system(self) -> None:
        """Hai thu co vong doi khac nhau.

        Bat he ben ngoai cau hinh lai moi lan nguoi van hanh doi mat khau la
        cach chac chan de co nguoi tat xac thuc cho do phien.
        """
        self.dang_nhap()
        self.c.post("/quan-tri/doi-mat-khau",
                    data={"cu": MAT_KHAU, "moi": "mot cau khac du dai 2027",
                          "lai": "mot cau khac du dai 2027"})
        self.assertEqual(self.gui().status_code, 200)

    def test_a_new_ticket_kills_the_old_one(self) -> None:
        self.dang_nhap()
        self.c.post("/epg/ve-moi")
        self.assertEqual(self.gui().status_code, 401)
        moi = A.load(self.auth_file).token
        self.assertNotEqual(moi, self.ve)
        r = self.c.post("/api/epg", content=self.xml,
                        headers={"Authorization": f"Bearer {moi}"})
        self.assertEqual(r.status_code, 200)


class TestNothingBadReachesTheInbox(EpgCase):
    """Kiem TRUOC khi ghi.

    File hong nam trong hop thu se lam hong lan sinh EIT ke tiep, ma lan do
    xay ra vai giay sau va khong ai dang nhin.
    """

    def test_an_empty_body(self) -> None:
        r = self.gui(b"")
        self.assertEqual(r.status_code, 400)
        self.assertIn("rỗng", r.json()["loi"])
        self.assertEqual(self.trong_hop(), [])

    def test_something_that_is_not_xml(self) -> None:
        r = self.gui(b"day khong phai xml")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.trong_hop(), [])

    def test_xml_that_is_not_a_schedule(self) -> None:
        r = self.gui(b"<html><body>oops</body></html>")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.trong_hop(), [])

    def test_a_schedule_with_no_events(self) -> None:
        r = self.gui(b"<PSI><NETWORK id='1'/></PSI>")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.trong_hop(), [])

    def test_bytes_that_are_not_utf8(self) -> None:
        r = self.gui(b"\xff\xfe khong phai utf-8")
        self.assertEqual(r.status_code, 400)
        self.assertIn("UTF-8", r.json()["loi"])
        self.assertEqual(self.trong_hop(), [])

    def test_a_bad_file_never_replaces_a_good_one(self) -> None:
        """Ca dang so nhat: da co lich tot, ben kia gui ve mot file hong."""
        self.gui()
        tot = (self.inbox / self.trong_hop()[0]).read_bytes()
        ten = self.trong_hop()[0]
        self.gui(b"<html/>", ten=ten)
        self.assertEqual((self.inbox / ten).read_bytes(), tot)

    def test_a_path_that_tries_to_escape(self) -> None:
        for xau in ("../thoat.xml", "../../thoat.xml", "a/b.xml",
                    chr(92) + "windows.xml", ".giau"):
            with self.subTest(xau=xau):
                r = self.gui(ten=xau)
                self.assertEqual(r.status_code, 400)
                self.assertIn("không hợp lệ", r.json()["loi"])
        self.assertEqual(self.trong_hop(), [])


class TestAcceptingAFile(EpgCase):
    def test_it_lands_in_the_inbox(self) -> None:
        r = self.gui()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.trong_hop(), [r.json()["ten"]])

    def test_the_name_comes_from_the_earliest_event(self) -> None:
        """Nho vay gui lai cung mot ngay la ghi de dung file cu."""
        self.assertEqual(self.gui().json()["ten"], "2026-09-08.xml")

    def test_sending_twice_does_not_leave_a_duplicate(self) -> None:
        self.gui()
        self.gui()
        self.assertEqual(len(self.trong_hop()), 1)

    def test_an_explicit_name_is_honoured(self) -> None:
        self.assertEqual(self.gui(ten="ngay-mai.xml").json()["ten"], "ngay-mai.xml")

    def test_a_name_without_the_suffix_gets_one(self) -> None:
        self.assertEqual(self.gui(ten="ngay-mai").json()["ten"], "ngay-mai.xml")

    def test_the_answer_says_enough_for_the_caller_to_log_it(self) -> None:
        d = self.gui().json()
        for khoa in ("nhan", "ten", "ts_id", "so_dich_vu", "so_su_kien",
                     "tu", "den", "sinh_lai"):
            with self.subTest(khoa=khoa):
                self.assertIn(khoa, d)
        self.assertEqual(d["ts_id"], 8)
        self.assertGreater(d["so_su_kien"], 100)

    def test_it_regenerates_immediately(self) -> None:
        """Ca ly do ton tai cua tuyen nay: nhan xong la len song, khong cho."""
        self.assertFalse(self.build.exists())
        self.gui()
        self.assertTrue((self.build / "nit.xml").exists())
        self.assertEqual(len(list(self.build.glob("*.xml"))), 10)

    def test_the_file_on_disk_is_what_was_sent(self) -> None:
        r = self.gui()
        got = (self.inbox / r.json()["ten"]).read_text(encoding="utf-8")
        self.assertEqual(got, self.xml.decode("utf-8"))


class TestThePage(EpgCase):
    def test_it_needs_a_login(self) -> None:
        r = self.c.get("/epg")
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].startswith("/dang-nhap"))

    def test_an_empty_inbox_says_so(self) -> None:
        self.dang_nhap()
        page = self.c.get("/epg").text
        self.assertIn("Hộp thư trống", page)
        self.assertIn("mất NIT mới là mất kênh", page)

    def test_it_lists_what_arrived(self) -> None:
        self.gui()
        self.dang_nhap()
        page = self.c.get("/epg").text
        self.assertIn("2026-09-08.xml", page)
        self.assertIn(">44<", page)      # so dich vu

    def test_it_shows_the_ticket_and_a_worked_example(self) -> None:
        self.dang_nhap()
        page = self.c.get("/epg").text
        self.assertIn(self.ve, page)
        self.assertIn("/api/epg", page)
        self.assertIn("Authorization: Bearer", page)

    def test_a_broken_file_is_named_not_hidden(self) -> None:
        """Trang nay chinh la cho nguoi ta toi khi nghi mot file co van de."""
        self.inbox.mkdir(parents=True, exist_ok=True)
        (self.inbox / "hong.xml").write_text("<html/>", encoding="utf-8")
        self.dang_nhap()
        page = self.c.get("/epg").text
        self.assertIn("hong.xml", page)
        self.assertIn("không đọc được", page)

    def test_uploading_by_hand_takes_the_same_road(self) -> None:
        self.dang_nhap()
        r = self.c.post("/epg/tai-len",
                        files={"file": ("lich.xml", self.xml, "application/xml")})
        self.assertIn("đã nhận", self.said(r))
        self.assertEqual(self.trong_hop(), ["2026-09-08.xml"])

    def test_uploading_a_broken_file_by_hand_is_refused_too(self) -> None:
        self.dang_nhap()
        r = self.c.post("/epg/tai-len",
                        files={"file": ("hong.xml", b"<html/>", "application/xml")})
        self.assertIn("không phân tích được", self.said(r))
        self.assertEqual(self.trong_hop(), [])

    def test_uploading_nothing_is_refused(self) -> None:
        self.dang_nhap()
        r = self.c.post("/epg/tai-len", data={"ten": "x.xml"})
        self.assertIn("chưa chọn file", self.said(r))

    def test_deleting_a_file(self) -> None:
        self.gui()
        self.dang_nhap()
        r = self.c.post("/epg/xoa", data={"ten": "2026-09-08.xml"})
        self.assertIn("đã xoá", self.said(r))
        self.assertEqual(self.trong_hop(), [])

    def test_deleting_something_that_is_not_there(self) -> None:
        self.dang_nhap()
        r = self.c.post("/epg/xoa", data={"ten": "khong-co.xml"})
        self.assertIn("không có file", self.said(r))

    def test_deleting_cannot_reach_outside_the_inbox(self) -> None:
        self.dang_nhap()
        r = self.c.post("/epg/xoa", data={"ten": "../config/network.yaml"})
        self.assertIn("không có file", self.said(r))
        self.assertTrue((self.dir / "network.yaml").exists())


if __name__ == "__main__":
    unittest.main()
