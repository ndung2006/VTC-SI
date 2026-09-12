"""Đăng nhập, phiên làm việc, đổi mật khẩu — vỏ có I/O.

Không dùng thư viện ngoài. ``hashlib.scrypt`` và ``hmac.compare_digest`` của
thư viện chuẩn đủ mạnh và đã có sẵn, nên thêm ``passlib`` hay ``bcrypt`` chỉ
tăng bề mặt phụ thuộc cho một hệ mà **cả đường ra sóng phải chạy được khi
không cài gì thêm**.

Ba quyết định đáng giải thích.

**Mật khẩu đầu tiên chỉ đặt được từ terminal** — ``vtcsi passwd``. Không có
trang "tạo tài khoản lần đầu" trên web, vì trang đó nghĩa là *ai chạm tới cổng
trước thì người đó làm chủ*. Người có quyền shell trên máy phát mới là chủ hợp
pháp; đó là ranh giới có sẵn và ta dùng lại nó.

**File mật khẩu không nằm trong git.** Cấu hình báo hiệu thì phải nằm trong git
— đó là cơ chế đồng bộ. Băm mật khẩu thì ngược lại: vào git một lần là nằm
trong lịch sử mãi mãi, kể cả sau khi xoá. Vì thế mặc định là
``.vtcsi-auth.json`` ở gốc kho và ``.gitignore`` có nó; trang quản trị còn
**tự kiểm tra lại** bằng ``git check-ignore`` và kêu to nếu sai.

**Phiên là cookie có chữ ký, không phải bảng trong bộ nhớ.** Bảng trong bộ nhớ
mất sạch mỗi lần khởi động lại tiến trình, mà ``vtcsi run`` được thiết kế để
khởi động lại mà không ai để ý. Cookie ký bằng một khoá nằm cùng file mật khẩu,
nên **đổi mật khẩu là đăng xuất mọi nơi** — đúng điều người ta mong đợi khi họ
đổi mật khẩu vì nghi bị lộ.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, replace
from hashlib import scrypt, sha256
from pathlib import Path

AUTH_FILE = ".vtcsi-auth.json"
"""Tên mặc định, đặt ở gốc kho và phải nằm trong ``.gitignore``."""

COOKIE = "vtcsi_phien"

#: Tham số scrypt. n=2^15 tốn chừng 100 ms và 32 MB — đủ chậm để dò mò là vô
#: vọng, đủ nhanh để người đăng nhập không thấy khựng.
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32

TOKEN_BYTES = 32
"""Vé máy dài 32 byte ngẫu nhiên — không có gì để đoán."""

DEFAULT_USER = "admin"
"""Tên đăng nhập mặc định."""

MIN_LENGTH = 12
"""Chỉ đòi **độ dài**, không đòi phải có chữ hoa và ký tự lạ.

Luật "phải có ký tự đặc biệt" đẩy người ta tới ``Vtc@2026`` — ngắn, đoán được,
và dán trên màn hình. Một câu dài dễ nhớ mạnh hơn nhiều.
"""

MAX_AGE = 12 * 3600
"""Phiên sống 12 giờ — dài hơn một ca trực, ngắn hơn một ngày."""

LOCK_AFTER = 5
LOCK_SECONDS = 60.0
"""Sai 5 lần thì khoá 1 phút. Không khoá vĩnh viễn: hệ này chỉ có một người
dùng, khoá cứng nghĩa là tự nhốt mình ra ngoài đúng lúc đang có sự cố."""


class AuthError(ValueError):
    """Thao tác xác thực bị từ chối. Thông điệp đi thẳng ra giao diện."""


@dataclass(frozen=True, slots=True)
class Credentials:
    user: str
    salt: bytes
    digest: bytes
    secret: bytes
    changed_at: float
    n: int = SCRYPT_N
    r: int = SCRYPT_R
    p: int = SCRYPT_P
    token: str = ""
    """Vé cho **máy**, không phải cho người.

    Hệ lập lịch bên ngoài đẩy XML qua HTTPS; nó không gõ mật khẩu vào ô đăng
    nhập được. Nên nó dùng một chuỗi ngẫu nhiên dài, gửi trong header.

    Để cùng file với mật khẩu vì cùng một lý do: không được vào git. Nhưng
    **đổi mật khẩu không đổi vé này** — hai thứ có vòng đời khác nhau, và bắt
    hệ bên ngoài cấu hình lại mỗi lần người vận hành đổi mật khẩu là cách chắc
    chắn để có người tắt xác thực cho đỡ phiền.
    """


# ---------------------------------------------------------------- mật khẩu


def _derive(password: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    return scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                  dklen=KEY_LEN, maxmem=64 * 1024 * 1024)


def check_strength(password: str, user: str = "") -> None:
    """Từ chối những mật khẩu hỏng theo cách dễ thấy nhất. Không hơn."""
    if len(password) < MIN_LENGTH:
        raise AuthError(
            f"mật khẩu phải dài ít nhất {MIN_LENGTH} ký tự — đang có "
            f"{len(password)}. Một câu dễ nhớ mạnh hơn một chuỗi ký tự lạ ngắn.")
    if user and password.strip().lower() == user.strip().lower():
        raise AuthError("mật khẩu không được trùng tên đăng nhập")
    if password != password.strip():
        raise AuthError("mật khẩu có dấu cách ở đầu hoặc cuối — gần như chắc "
                        "chắn là gõ nhầm, và sẽ rất khó tìm ra sau này")


def make(user: str, password: str) -> Credentials:
    """Tạo bộ thông tin đăng nhập mới. Sinh luôn khoá ký phiên."""
    user = user.strip()
    if not user:
        raise AuthError("thiếu tên đăng nhập")
    check_strength(password, user)
    salt = secrets.token_bytes(16)
    return Credentials(
        user=user,
        salt=salt,
        digest=_derive(password, salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P),
        secret=secrets.token_bytes(32),
        changed_at=time.time(),
        token=new_token(),
    )


def new_token() -> str:
    """Vé mới cho hệ bên ngoài."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_ok(cred: Credentials, given: str) -> bool:
    """So vé **hằng thời gian**. Chưa cấp vé thì mọi vé đều sai."""
    if not cred.token or not given:
        return False
    return hmac.compare_digest(given.encode("utf-8"), cred.token.encode("utf-8"))


def verify(cred: Credentials, user: str, password: str) -> bool:
    """So sánh **hằng thời gian** cả tên lẫn mật khẩu.

    Vẫn tính băm ngay cả khi tên đã sai, để thời gian trả lời không tiết lộ
    tên đăng nhập nào tồn tại.
    """
    got = _derive(password, cred.salt, n=cred.n, r=cred.r, p=cred.p)
    ok_pass = hmac.compare_digest(got, cred.digest)
    ok_user = hmac.compare_digest(user.strip().encode("utf-8"),
                                  cred.user.encode("utf-8"))
    return ok_user and ok_pass


def change(cred: Credentials, old: str, new: str) -> Credentials:
    """Đổi mật khẩu. Khoá ký phiên **đổi theo**, nên mọi phiên cũ hết hiệu lực."""
    if not verify(cred, cred.user, old):
        raise AuthError("mật khẩu hiện tại không đúng")
    if old == new:
        raise AuthError("mật khẩu mới trùng mật khẩu cũ")
    check_strength(new, cred.user)
    salt = secrets.token_bytes(16)
    return replace(
        cred,
        salt=salt,
        digest=_derive(new, salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P),
        secret=secrets.token_bytes(32),
        changed_at=time.time(),
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
    )


# ------------------------------------------------------------------ phiên


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue(cred: Credentials, *, now: float) -> str:
    """Một vé phiên: ``tên.hạn.chữ-ký``."""
    until = int(now + MAX_AGE)
    body = f"{_b64(cred.user.encode())}.{until}"
    sig = hmac.new(cred.secret, body.encode("ascii"), sha256).digest()
    return f"{body}.{_b64(sig)}"


def read(cred: Credentials, token: str, *, now: float) -> str | None:
    """Tên người dùng nếu vé còn hợp lệ, ``None`` nếu không. Không ném lỗi.

    Không ném lỗi là cố ý: một vé hỏng, hết hạn, hay bị sửa đều dẫn tới cùng
    một chỗ — trang đăng nhập. Phân biệt chúng chỉ giúp người đang thử mò.
    """
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    body = f"{parts[0]}.{parts[1]}"
    try:
        want = hmac.new(cred.secret, body.encode("ascii"), sha256).digest()
        if not hmac.compare_digest(_unb64(parts[2]), want):
            return None
        if int(parts[1]) < now:
            return None
        return _unb64(parts[0]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


# ------------------------------------------------------------------- đĩa


def path_for(root: Path) -> Path:
    return root / AUTH_FILE


def load(path: Path) -> Credentials | None:
    """Đọc file, hoặc ``None`` nếu chưa có. File hỏng thì **ném lỗi**.

    Phân biệt hai ca: *chưa đặt mật khẩu* dẫn tới hướng dẫn chạy
    ``vtcsi passwd``; *file hỏng* là sự cố và không được im lặng coi như chưa
    đặt — nếu không, một file JSON lỗi sẽ âm thầm mở toang giao diện.
    """
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return Credentials(
            user=d["user"],
            salt=bytes.fromhex(d["salt"]),
            digest=bytes.fromhex(d["digest"]),
            secret=bytes.fromhex(d["secret"]),
            changed_at=float(d["changed_at"]),
            n=int(d.get("n", SCRYPT_N)),
            r=int(d.get("r", SCRYPT_R)),
            p=int(d.get("p", SCRYPT_P)),
            token=str(d.get("token", "")),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise AuthError(f"file đăng nhập hỏng: {path} — {exc}") from exc


def save(path: Path, cred: Credentials) -> None:
    """Ghi file, chỉ chủ sở hữu đọc được."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({
        "user": cred.user,
        "salt": cred.salt.hex(),
        "digest": cred.digest.hex(),
        "secret": cred.secret.hex(),
        "changed_at": cred.changed_at,
        "n": cred.n, "r": cred.r, "p": cred.p,
        "token": cred.token,
    }, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(body + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:  # pragma: no cover — Windows khong co khai niem nay
        pass
    tmp.replace(path)


# ------------------------------------------------------- chống dò mật khẩu


@dataclass(slots=True)
class Gate:
    """Đếm số lần sai và khoá tạm thời.

    Không khoá vĩnh viễn: hệ chỉ có một người dùng, khoá cứng nghĩa là tự nhốt
    mình ra ngoài đúng lúc đang có sự cố cần sửa gấp.
    """

    failures: int = 0
    locked_until: float = 0.0

    def locked_for(self, now: float) -> float:
        return max(0.0, self.locked_until - now)

    def fail(self, now: float) -> None:
        self.failures += 1
        if self.failures >= LOCK_AFTER:
            self.locked_until = now + LOCK_SECONDS
            self.failures = 0

    def succeed(self) -> None:
        self.failures = 0
        self.locked_until = 0.0
