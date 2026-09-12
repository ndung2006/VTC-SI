"""Lấy **bản gieo** thay vì cấu hình đang sửa.

Vì sao cần: vài bài test khẳng định "cấu hình khớp với sóng". Khi ``config/``
còn là bản gieo đóng băng thì đọc thẳng thư mục là đúng. Từ lúc có giao diện
nhập liệu thì không còn đúng nữa — thư mục đó **cốt để sửa**, và một thao tác
hợp lệ của người vận hành sẽ làm đỏ bộ test. Cảnh báo đỏ vì lý do bình thường
là cảnh báo sắp bị ngó lơ.

Thứ các bài đó thực sự muốn nói là *"bản gieo khớp với sóng"*.

**Bản gieo là một cái thẻ, không phải HEAD.** Đây là bài học phải trả giá mới
có: bản đầu của file này bung ``config/`` từ HEAD, vì lúc viết thì HEAD *chính
là* bản gieo. Tới ngày người vận hành commit thay đổi thật đầu tiên — tăng
version, tắt EPG kênh 801 và 802, sửa vài số kênh — thì HEAD thôi là bản gieo,
và **15 bài đỏ cùng lúc, trong đó có cả bảy bài so byte**. Không bài nào trong
số đó tìm ra lỗi gì; chúng chỉ đang nói rằng cấu hình hôm nay khác cấu hình
hôm gieo, mà điều đó thì đúng và là chuyện bình thường.

Hai câu hỏi khác nhau, và trộn chúng vào nhau là gốc của chuyện đó:

* *"Bộ sinh có dựng lại đúng từng byte các bảng bóc từ sóng, từ chính cấu hình
  đọc ra từ sóng không?"* — AC-1 và AC-2. Câu trả lời **không được phép đổi**,
  nên mốc đối chiếu phải đứng yên: thẻ ``gieo``.
* *"Cấu hình hôm nay đã lệch khỏi sóng chưa?"* — câu hỏi vận hành, đổi theo
  từng ngày, và trả lời nó là việc của ``vtcsi preflight``. Nó làm tốt hơn bộ
  test, vì nó phân biệt được *đổi ngầm* với *tăng version thừa*.

Đổi thẻ ``gieo`` chỉ khi gieo lại từ một bản thu sóng **mới** — và đó phải là
một hành động cố ý, có người duyệt.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent

THE = "gieo"
"""Thẻ git trỏ tới commit gieo cấu hình từ sóng."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT),
                          capture_output=True, timeout=60)


def committed_config() -> tempfile.TemporaryDirectory:
    """Bung ``config/`` tại thẻ ``gieo`` ra một thư mục tạm.

    Trả về chính đối tượng ``TemporaryDirectory`` để nơi gọi giữ và dọn; thư
    mục cấu hình là ``Path(td.name) / "config"``.
    """
    if _git("rev-parse", "--git-dir").returncode != 0:
        raise unittest.SkipTest(
            "chua phai kho git — khong co ban gieo de doi chieu")

    if _git("rev-parse", "--verify", f"{THE}^{{commit}}").returncode != 0:
        # KHONG bo qua. Bo qua o day la cach ma bay bai so byte tung ngu yen
        # nhieu phien lien ma khong ai biet — mot bai bo qua vi moi truong
        # trong y het mot bai bo qua vi chua cai gi.
        raise AssertionError(
            f"khong tim thay the git {THE!r}.\n"
            "  The nay ghim ban cau hinh gieo tu song — moc doi chieu cua cac\n"
            "  bai so byte. Thieu no thi khong con chuan vang nao ca.\n"
            f"  Neu vua clone: git fetch --tags\n"
            f"  Neu that su chua co: git tag -a {THE} <commit-gieo>")

    r = _git("archive", "--format=tar", THE, "config")
    if r.returncode != 0:
        raise AssertionError(
            f"the {THE!r} khong co thu muc config/: "
            + r.stderr.decode("utf-8", "replace").strip())

    td = tempfile.TemporaryDirectory()
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        tar.extractall(td.name, filter="data")
    if not (Path(td.name) / "config" / "network.yaml").exists():
        td.cleanup()
        raise AssertionError(f"the {THE!r} khong co config/network.yaml")
    return td
