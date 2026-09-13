"""Thao tác git trên thư mục cấu hình — vỏ có I/O.

Git là **cơ chế đồng bộ của hệ thống** (§3.3 của ``spec.md``), nên giao diện
nhập liệu không được ghi file rồi để đó: mỗi thay đổi phải thành một commit có
tác giả và lý do. Đó là thứ mà tình trạng *"config changed on both"* của
Barrowa đang thiếu.

Hỏng theo hướng mở: thư mục chưa phải kho git thì vẫn ghi được file, chỉ mất
phần lịch sử — và giao diện nói rõ điều đó thay vì từ chối làm việc.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Status:
    is_repo: bool
    dirty: tuple[str, ...] = ()
    head: str = ""
    message: str = ""

    @property
    def clean(self) -> bool:
        return self.is_repo and not self.dirty


def _run(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True,
        timeout=30, check=check, encoding="utf-8", errors="replace",
    )


def status(root: Path) -> Status:
    """Trạng thái kho, hoặc ``is_repo=False`` nếu chưa khởi tạo."""
    r = _run(root, "rev-parse", "--is-inside-work-tree")
    if r.returncode != 0:
        return Status(is_repo=False, message="thu muc nay chua phai kho git")

    dirty = tuple(
        line[3:].strip()
        for line in _run(root, "status", "--porcelain").stdout.splitlines()
        if line.strip()
    )
    log = _run(root, "log", "-1", "--pretty=%h %s")
    return Status(
        is_repo=True,
        dirty=dirty,
        head=log.stdout.strip() if log.returncode == 0 else "(chua co commit nao)",
    )


def diff(root: Path, paths: list[str] | None = None) -> str:
    """Khác biệt chưa commit, dạng văn bản."""
    args = ["diff", "--no-color"]
    if paths:
        args += ["--"] + paths
    r = _run(root, *args)
    if r.returncode != 0:
        return ""
    if r.stdout.strip():
        return r.stdout
    # File moi chua duoc theo doi thi khong hien trong `git diff`.
    untracked = _run(root, "ls-files", "--others", "--exclude-standard").stdout.strip()
    return ("file moi chua theo doi:\n" + untracked) if untracked else ""


def is_ignored(root: Path, path: Path) -> bool | None:
    """``path`` có nằm ngoài tầm git không. ``None`` nếu không hỏi được.

    Dùng cho đúng một chỗ: file mật khẩu. Băm mật khẩu lọt vào git là nằm
    trong lịch sử **mãi mãi**, kể cả sau khi xoá file đi — nên câu hỏi này
    đáng được hỏi bằng chính git chứ không phải bằng niềm tin vào
    ``.gitignore``.
    """
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        return True  # ngoai kho thi git khong dong toi duoc
    r = _run(root, "check-ignore", "-q", "--", rel)
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    return None


def commit(root: Path, message: str, author: str, paths: list[str]) -> tuple[bool, str]:
    """Đưa vào chỉ mục rồi commit. Trả về ``(thành công, thông báo)``.

    ``author`` đi vào trường tác giả của commit chứ không chỉ nằm trong lời
    nhắn: câu hỏi "ai đổi cái này" phải trả lời được bằng ``git log``.
    """
    if not message.strip():
        return False, "thieu ly do thay doi"
    if not author.strip():
        return False, "thieu ten nguoi thuc hien"

    st = status(root)
    if not st.is_repo:
        return False, "chua phai kho git — file da duoc ghi, nhung khong co lich su"

    add = _run(root, "add", "--", *paths)
    if add.returncode != 0:
        return False, add.stderr.strip() or "khong dua vao chi muc duoc"

    if not _run(root, "diff", "--cached", "--quiet").returncode:
        return False, "khong co gi de commit"

    r = _run(root, "-c", f"user.name={author}",
             "-c", "user.email=vtcsi@local",
             "commit", "-m", message.strip())
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[:400]
    return True, _run(root, "log", "-1", "--pretty=%h %s").stdout.strip()


def init(root: Path) -> tuple[bool, str]:
    """Khởi tạo kho, cho trường hợp chạy lần đầu."""
    if status(root).is_repo:
        return False, "da la kho git roi"
    r = _run(root, "init")
    return (r.returncode == 0), (r.stdout or r.stderr).strip()


def config_at_head(root: Path, sub: str = "config"):
    """Bung ``config/`` tại HEAD ra thư mục tạm, trả về đường dẫn.

    Trả ``None`` khi chưa phải kho git, chưa có commit nào, hoặc HEAD không có
    thư mục đó — nghĩa là **không có mốc để so**. Nơi gọi phải xử lý ``None``
    bằng cách không làm gì, chứ không phải bằng cách đoán: tăng version dựa
    trên một mốc tưởng tượng còn tệ hơn không tăng.

    Nơi gọi giữ đối tượng trả về cho tới khi dùng xong; thư mục tạm bị xoá khi
    nó bị thu hồi.
    """
    import io as _io
    import tarfile
    import tempfile

    # KHONG dung `_run`: no giai ma text, ma tar la nhi phan — giai ma xong
    # la hong file, va hong mot cach im lang chu khong bao loi.
    r = subprocess.run(["git", "archive", "--format=tar", "HEAD", sub],
                       cwd=str(root), capture_output=True, timeout=30)
    if r.returncode != 0:
        return None
    td = tempfile.TemporaryDirectory()
    try:
        with tarfile.open(fileobj=_io.BytesIO(r.stdout)) as tar:
            tar.extractall(td.name, filter="data")
    except (tarfile.TarError, ValueError):
        td.cleanup()
        return None
    if not (Path(td.name) / sub).is_dir():
        td.cleanup()
        return None
    return td
