"""Tìm công cụ TSDuck, kể cả khi nó không nằm trên ``PATH``.

Tên file có hậu tố ``_path`` chứ không phải ``tsduck.py`` gọn hơn, vì
``vtcsi.tables.tsduck`` đã tồn tại và ``test_binary.py`` dùng cả hai — hai cái
tên giống nhau trong một file là cái bẫy đặt sẵn cho người đọc sau.

Vì sao cần cả một file cho việc này: bảy bài so byte — **phép thử mạnh nhất
của cả dự án** — đã im lặng bị bỏ qua suốt nhiều phiên làm việc, chỉ vì
``shutil.which("tstabcomp")`` trả về ``None``. TSDuck đã cài sẵn từ đầu; nó chỉ
không có trong ``PATH`` của Git Bash, trong khi PowerShell thì thấy.

Một bài test bị bỏ qua vì lý do môi trường trông giống hệt một bài test bị bỏ
qua vì chưa cài gì — và cả hai đều in ra chữ ``s`` màu xám. Nên ở đây ta **tìm
thêm ở những chỗ TSDuck thường nằm**, và khi vẫn không thấy thì nói rõ đã tìm
ở đâu, thay vì chỉ nói "chưa cài TSDuck".
"""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path

#: Chỗ trình cài đặt của TSDuck đặt tệp, theo từng hệ.
NOI_THUONG_NAM = (
    Path("C:/Program Files/TSDuck/bin"),
    Path("C:/Program Files (x86)/TSDuck/bin"),
    Path("/usr/bin"),
    Path("/usr/local/bin"),
    Path("/opt/tsduck/bin"),
)


def find(tool: str) -> str | None:
    """Đường dẫn đầy đủ tới một công cụ TSDuck, hoặc ``None``."""
    found = shutil.which(tool)
    if found:
        return found
    for thu_muc in NOI_THUONG_NAM:
        for ten in (tool, tool + ".exe"):
            ung_vien = thu_muc / ten
            if ung_vien.is_file():
                return str(ung_vien)
    return None


def require(tool: str) -> str:
    """Như ``find``, nhưng bỏ qua bài test kèm **chỗ đã tìm**.

    Thông điệp dài hơn mức thường thấy là cố ý: lần trước thông điệp ngắn gọn
    "chua cai TSDuck" đã khiến bảy bài quan trọng nhất ngủ yên trong khi công
    cụ nằm ngay trên máy.
    """
    found = find(tool)
    if found:
        return found
    da_tim = ", ".join(str(x) for x in NOI_THUONG_NAM)
    raise unittest.SkipTest(
        f"khong tim thay '{tool}'. Da tim trong PATH va: {da_tim}. "
        f"Neu TSDuck da cai o cho khac, them thu muc bin cua no vao PATH "
        f"roi chay lai."
    )


def on_path() -> dict[str, str]:
    """Môi trường có thư mục bin của TSDuck, để truyền cho ``subprocess``.

    Cần vì ``tsp`` gọi tiếp các plugin của chính nó; gọi ``tsp`` bằng đường dẫn
    đầy đủ mà không có thư mục đó trong ``PATH`` là kiểu hỏng chỉ lộ ra ở bài
    test nào thật sự chạy ``tsp``.
    """
    env = dict(os.environ)
    found = find("tsp")
    if found:
        bin_dir = str(Path(found).parent)
        if bin_dir not in env.get("PATH", ""):
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env
