"""Lấy cấu hình **đã commit** thay vì cấu hình đang sửa.

Vì sao cần: vài bài test khẳng định "cấu hình khớp với sóng". Khi `config/`
còn là bản gieo đóng băng thì đọc thẳng thư mục là đúng. Từ lúc có giao diện
nhập liệu thì không còn đúng nữa — thư mục đó **cốt để sửa**, và một thao tác
hợp lệ của người vận hành sẽ làm đỏ bộ test. Cảnh báo đỏ vì lý do bình thường
là cảnh báo sắp bị ngó lơ.

Thứ các bài đó thực sự muốn nói là *"bản gieo khớp với sóng"*, mà bản gieo
nằm ở HEAD chứ không nằm trong thư mục làm việc. Nên ta bung `config/` từ HEAD
ra một thư mục tạm và đọc chỗ đó.

Việc phát hiện cấu hình đang sửa đã lệch khỏi sóng là của ``vtcsi preflight``,
không phải của bộ test — và nó làm việc đó tốt hơn, vì nó phân biệt được
*đổi ngầm* với *tăng thừa*.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent


def committed_config() -> tempfile.TemporaryDirectory:
    """Bung ``config/`` từ HEAD ra thư mục tạm.

    Trả về chính đối tượng ``TemporaryDirectory`` để nơi gọi giữ và dọn; thư
    mục cấu hình là ``Path(td.name) / "config"``.

    Bỏ qua bài test nếu chưa phải kho git hoặc chưa có commit nào — lúc đó
    không có "bản đã commit" nào để mà nói tới.
    """
    r = subprocess.run(["git", "archive", "--format=tar", "HEAD", "config"],
                       cwd=str(ROOT), capture_output=True, timeout=60)
    if r.returncode != 0:
        raise unittest.SkipTest(
            "chua phai kho git hoac chua co commit nao — khong co ban gieo "
            "da commit de doi chieu")

    td = tempfile.TemporaryDirectory()
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        tar.extractall(td.name, filter="data")
    if not (Path(td.name) / "config" / "network.yaml").exists():
        td.cleanup()
        raise unittest.SkipTest("HEAD khong co config/network.yaml")
    return td
