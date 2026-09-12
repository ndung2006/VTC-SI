"""Đăng nhập, phiên, đổi mật khẩu.

Đây là bộ **duy nhất** chạy với xác thực bật. Các bộ web khác tắt nó đi vì
chúng kiểm việc sửa cấu hình chứ không kiểm đăng nhập, và mỗi lần đăng nhập
tốn ~100 ms scrypt. Đổi lại, bài ``TestLoginIsOnByDefault`` ở đây phải ghim
cho chắc rằng mặc định là **bật** — nếu không, cả kiến trúc test kia trở thành
một cái bẫy: mọi thứ xanh trong khi giao diện thật mở toang.

Mật khẩu dùng trong bài cố tình dài và tầm thường; chúng chỉ là dữ liệu thử.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

import seed
from vtcsi.web import auth as A

MAT_KHAU = "mot cau dai de nho 2026"
KHAC = "mot cau khac cung du dai 2027"
NGUOI = "dung"


class AuthCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest("chua cai fastapi")
        cls._seed = seed.committed_config()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._seed.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "config"
        shutil.copytree(Path(self._seed.name) / "config", self.dir)
        self.auth_file = self.root / ".vtcsi-auth.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------------- tro giup

    def client(self, *, require_login: bool = True) -> TestClient:
        from vtcsi.web.app import create_app
        return TestClient(
            create_app(self.dir, self.root, auth_file=self.auth_file,
                       require_login=require_login),
            follow_redirects=False)

    def with_password(self, password: str = MAT_KHAU) -> TestClient:
        A.save(self.auth_file, A.make(NGUOI, password))
        return self.client()

    def logged_in(self, password: str = MAT_KHAU) -> TestClient:
        c = self.with_password(password)
        r = c.post("/dang-nhap",
                   data={"user": NGUOI, "password": password, "tiep": "/"})
        self.assertEqual(r.status_code, 303, "dang nhap that bai")
        c.cookies.update(r.cookies)
        return c

    def said(self, r) -> str:
        q = parse_qs(urlparse(r.headers.get("location", "")).query)
        return (q.get("note") or q.get("err") or [""])[0]

    #: Mọi tuyến đường phải đóng khi chưa đăng nhập.
    KIN = ("/", "/ts/8", "/ts/8/new", "/linkage", "/linkage/nit/0",
           "/bouquet/6510", "/thay-doi", "/quan-tri")


class TestLoginIsOnByDefault(AuthCase):
    """Bai quan trong nhat ca file.

    Cac bo test web khac chay voi `require_login=False`. Neu mac dinh that su
    la tat, ca kien truc do thanh mot cai bay: moi thu xanh trong khi giao dien
    that mo toang.
    """

    def test_create_app_defaults_to_requiring_login(self) -> None:
        from vtcsi.web.app import create_app
        c = TestClient(create_app(self.dir, self.root,
                                  auth_file=self.auth_file),
                       follow_redirects=False)
        A.save(self.auth_file, A.make(NGUOI, MAT_KHAU))
        self.assertEqual(c.get("/").status_code, 303)

    def test_the_banner_only_appears_when_auth_is_off(self) -> None:
        mo = self.client(require_login=False).get("/").text
        self.assertIn("không yêu cầu đăng nhập", mo)
        self.assertIn("--no-auth", mo)
        self.assertNotIn("không yêu cầu đăng nhập", self.logged_in().get("/").text)


class TestBeforeAPasswordExists(AuthCase):
    """Khong co trang "tao tai khoan lan dau" — ai cham cong truoc khong duoc
    lam chu."""

    def test_every_page_says_to_use_the_terminal(self) -> None:
        c = self.client()
        for url in self.KIN:
            with self.subTest(url=url):
                r = c.get(url)
                self.assertEqual(r.status_code, 503)
                self.assertIn("Chưa đặt mật khẩu", r.text)
                self.assertIn("vtcsi passwd", r.text)

    def test_writes_are_blocked_too(self) -> None:
        """Chan ca GET lan POST — chan moi GET la mot kieu chan gia."""
        c = self.client()
        before = (self.dir / "network.yaml").read_bytes()
        r = c.post("/version/set",
                   data={"table": "nit", "version": 9, "confirm": "9"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual((self.dir / "network.yaml").read_bytes(), before)

    def test_there_is_no_way_to_set_one_from_the_browser(self) -> None:
        page = self.client().get("/").text
        self.assertNotIn("<form", page)

    def test_a_corrupt_file_is_not_treated_as_absent(self) -> None:
        """File hong ma coi nhu chua dat thi mot loi JSON se mo toang giao dien."""
        self.auth_file.write_text("{ khong phai json", encoding="utf-8")
        r = self.client().get("/")
        self.assertEqual(r.status_code, 500)
        self.assertIn("Cấu hình không đọc được", r.text)


class TestLogin(AuthCase):
    def test_closed_pages_redirect_to_the_login(self) -> None:
        c = self.with_password()
        for url in self.KIN:
            with self.subTest(url=url):
                r = c.get(url)
                self.assertEqual(r.status_code, 303)
                self.assertTrue(r.headers["location"].startswith("/dang-nhap"))

    def test_it_remembers_where_you_were_going(self) -> None:
        c = self.with_password()
        r = c.get("/linkage/nit/0")
        self.assertIn("tiep=%2Flinkage%2Fnit%2F0", r.headers["location"])
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU,
                                       "tiep": "/linkage/nit/0"})
        self.assertEqual(r.headers["location"], "/linkage/nit/0")

    def test_an_offsite_destination_is_ignored(self) -> None:
        """`tiep` di thang vao Location — khong duoc de no tro ra ngoai."""
        c = self.with_password()
        for xau in ("https://vi-du.test/", "//vi-du.test/", "http://x"):
            with self.subTest(xau=xau):
                r = c.post("/dang-nhap", data={"user": NGUOI,
                                               "password": MAT_KHAU, "tiep": xau})
                self.assertEqual(r.headers["location"], "/")

    def test_a_wrong_password_is_refused(self) -> None:
        c = self.with_password()
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": "sai qua roi 123"})
        self.assertIn("không đúng", self.said(r))
        self.assertNotIn(A.COOKIE, r.cookies)

    def test_a_wrong_user_is_refused(self) -> None:
        c = self.with_password()
        r = c.post("/dang-nhap", data={"user": "ai do", "password": MAT_KHAU})
        self.assertIn("không đúng", self.said(r))

    def test_the_message_does_not_say_which_half_was_wrong(self) -> None:
        """Noi ra la xac nhan cho nguoi dang mo mot nua cau tra loi."""
        c = self.with_password()
        a = self.said(c.post("/dang-nhap",
                             data={"user": NGUOI, "password": "sai qua roi 123"}))
        b = self.said(c.post("/dang-nhap",
                             data={"user": "ai do", "password": MAT_KHAU}))
        self.assertEqual(a, b)

    def test_the_cookie_is_not_readable_by_scripts(self) -> None:
        c = self.with_password()
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        raw = r.headers["set-cookie"].lower()
        self.assertIn("httponly", raw)
        self.assertIn("samesite=lax", raw)

    def test_everything_opens_once_logged_in(self) -> None:
        c = self.logged_in()
        for url in self.KIN:
            with self.subTest(url=url):
                self.assertEqual(c.get(url).status_code, 200)

    def test_the_login_page_itself_is_always_reachable(self) -> None:
        self.assertEqual(self.with_password().get("/dang-nhap").status_code, 200)

    def test_a_logged_in_visitor_is_sent_home(self) -> None:
        self.assertEqual(self.logged_in().get("/dang-nhap").status_code, 303)


class TestSessions(AuthCase):
    def test_a_forged_ticket_is_refused(self) -> None:
        c = self.with_password()
        c.cookies.set(A.COOKIE, "ZHVuZw.99999999999.giamao")
        self.assertEqual(c.get("/").status_code, 303)

    def test_rubbish_in_the_cookie_does_not_crash(self) -> None:
        c = self.with_password()
        for xau in ("", "...", "a.b.c", "x" * 500, "ZHVuZw.khongphaiso.zzz"):
            with self.subTest(xau=xau):
                c.cookies.set(A.COOKIE, xau)
                self.assertEqual(c.get("/").status_code, 303)

    def test_a_ticket_signed_with_another_key_is_refused(self) -> None:
        khac = A.make(NGUOI, KHAC)
        c = self.with_password()
        c.cookies.set(A.COOKIE, A.issue(khac, now=time.time()))
        self.assertEqual(c.get("/").status_code, 303)

    def test_logging_out_clears_the_cookie(self) -> None:
        c = self.logged_in()
        self.assertEqual(c.get("/").status_code, 200)
        r = c.post("/dang-xuat")
        self.assertEqual(r.status_code, 303)
        c.cookies.clear()
        self.assertEqual(c.get("/").status_code, 303)


class TestChangingThePassword(AuthCase):
    def post(self, c, **data):
        return c.post("/quan-tri/doi-mat-khau", data=data)

    def test_it_works_and_logs_you_out_everywhere(self) -> None:
        """Doi mat khau vi nghi bi lo thi cat het phien la dieu nguoi ta mong."""
        c = self.logged_in()
        khac = self.client()
        khac.cookies.update(c.cookies)
        self.assertEqual(khac.get("/").status_code, 200)

        r = self.post(c, cu=MAT_KHAU, moi=KHAC, lai=KHAC)
        self.assertEqual(r.headers["location"], "/dang-nhap")
        self.assertEqual(khac.get("/").status_code, 303,
                         "phien o trinh duyet khac van con")

    def test_the_new_password_works(self) -> None:
        c = self.logged_in()
        self.post(c, cu=MAT_KHAU, moi=KHAC, lai=KHAC)
        c.cookies.clear()
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": KHAC})
        self.assertEqual(r.status_code, 303)
        self.assertIn(A.COOKIE, r.cookies)

    def test_the_old_password_stops_working(self) -> None:
        c = self.logged_in()
        self.post(c, cu=MAT_KHAU, moi=KHAC, lai=KHAC)
        c.cookies.clear()
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertIn("không đúng", self.said(r))

    def test_the_wrong_current_password_is_refused(self) -> None:
        c = self.logged_in()
        r = self.post(c, cu="sai qua roi 123", moi=KHAC, lai=KHAC)
        self.assertIn("hiện tại không đúng", self.said(r))
        self.assertTrue(A.verify(A.load(self.auth_file), NGUOI, MAT_KHAU))

    def test_a_mistyped_repeat_is_refused(self) -> None:
        c = self.logged_in()
        r = self.post(c, cu=MAT_KHAU, moi=KHAC, lai=KHAC + "x")
        self.assertIn("không giống nhau", self.said(r))
        self.assertTrue(A.verify(A.load(self.auth_file), NGUOI, MAT_KHAU))

    def test_a_short_password_is_refused(self) -> None:
        c = self.logged_in()
        r = self.post(c, cu=MAT_KHAU, moi="ngan", lai="ngan")
        self.assertIn(str(A.MIN_LENGTH), self.said(r))

    def test_reusing_the_same_password_is_refused(self) -> None:
        c = self.logged_in()
        r = self.post(c, cu=MAT_KHAU, moi=MAT_KHAU, lai=MAT_KHAU)
        self.assertIn("trùng mật khẩu cũ", self.said(r))

    def test_a_stranger_cannot_change_it(self) -> None:
        c = self.with_password()
        r = self.post(c, cu=MAT_KHAU, moi=KHAC, lai=KHAC)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].startswith("/dang-nhap"))
        self.assertTrue(A.verify(A.load(self.auth_file), NGUOI, MAT_KHAU))


class TestLockout(AuthCase):
    def test_it_locks_after_repeated_failures(self) -> None:
        c = self.with_password()
        for _ in range(A.LOCK_AFTER):
            c.post("/dang-nhap", data={"user": NGUOI, "password": "sai qua roi"})
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertIn("thử lại sau", self.said(r))

    def test_the_lock_is_temporary_not_permanent(self) -> None:
        """He chi co mot nguoi dung — khoa cung la tu nhot minh ra ngoai."""
        self.assertGreater(A.LOCK_SECONDS, 0)
        self.assertLess(A.LOCK_SECONDS, 3600)

    def test_a_success_clears_the_counter(self) -> None:
        c = self.with_password()
        for _ in range(A.LOCK_AFTER - 1):
            c.post("/dang-nhap", data={"user": NGUOI, "password": "sai qua roi"})
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertEqual(r.status_code, 303)
        c.cookies.clear()
        for _ in range(A.LOCK_AFTER - 1):
            c.post("/dang-nhap", data={"user": NGUOI, "password": "sai qua roi"})
        r = c.post("/dang-nhap", data={"user": NGUOI, "password": MAT_KHAU})
        self.assertNotIn("thử lại sau", self.said(r))


class TestTheAdminPage(AuthCase):
    def test_it_names_who_is_logged_in(self) -> None:
        self.assertIn(NGUOI, self.logged_in().get("/quan-tri").text)

    def test_it_shows_where_the_file_lives(self) -> None:
        self.assertIn(self.auth_file.name, self.logged_in().get("/quan-tri").text)

    def test_it_warns_when_the_file_is_inside_git(self) -> None:
        """Bam mat khau vao git la nam trong lich su mai mai."""
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.root, capture_output=True)
        page = self.logged_in().get("/quan-tri").text
        self.assertIn("nằm trong tầm của git", page)

    def test_it_is_quiet_when_the_file_is_ignored(self) -> None:
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.root, capture_output=True)
        (self.root / ".gitignore").write_text(self.auth_file.name + "\n",
                                              encoding="utf-8")
        page = self.logged_in().get("/quan-tri").text
        self.assertNotIn("nằm trong tầm của git", page)


class TestTheAuthFileItself(AuthCase):
    def test_the_plain_password_is_nowhere_in_it(self) -> None:
        A.save(self.auth_file, A.make(NGUOI, MAT_KHAU))
        raw = self.auth_file.read_text(encoding="utf-8")
        self.assertNotIn(MAT_KHAU, raw)

        # Chi soi nhung tu du dai VA co ky tu khong phai hex. Mot tu nhu "de"
        # toan ky tu hex se xuat hien tinh co trong bam — bat no la bao dong
        # gia, va bai test keu bua thi som muon bi tat.
        hex_chars = set("0123456789abcdefABCDEF")
        for tu in MAT_KHAU.split():
            if len(tu) < 4 or set(tu) <= hex_chars:
                continue
            with self.subTest(tu=tu):
                self.assertNotIn(tu, raw)

    def test_two_identical_passwords_hash_differently(self) -> None:
        """Muoi ngau nhien: hai he dat cung mat khau khong duoc giong nhau."""
        a = A.make(NGUOI, MAT_KHAU)
        b = A.make(NGUOI, MAT_KHAU)
        self.assertNotEqual(a.salt, b.salt)
        self.assertNotEqual(a.digest, b.digest)
        self.assertNotEqual(a.secret, b.secret)

    def test_it_survives_a_round_trip(self) -> None:
        made = A.make(NGUOI, MAT_KHAU)
        A.save(self.auth_file, made)
        self.assertEqual(A.load(self.auth_file), made)

    def test_a_missing_file_is_none_not_an_error(self) -> None:
        self.assertIsNone(A.load(self.auth_file))


if __name__ == "__main__":
    unittest.main()
