"""Đọc và ghi ``config/toc-do.yaml`` — vỏ có I/O.

File riêng, không nằm trong ``Config``: lý do ở đầu ``model/toc_do.py``.

Khác ``dau-ra.yaml`` ở một chỗ quan trọng: file này **vào git**. Địa chỉ ra bắt
buộc khác nhau giữa hai máy; nhịp lặp thì bắt buộc giống nhau, nếu không thì
hôm chuyển máy đầu thu thấy nhịp bảng đổi.

Thiếu file thì dùng mặc định chứ không lỗi — đó là bộ số đang chạy trên sóng,
nên một hệ chưa từng mở trang này vẫn phát đúng như trước.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path

import yaml

from vtcsi.model.toc_do import TocDo, TocDoError, validate

FILE = "toc-do.yaml"

_HEADER = """\
# Tốc độ dòng ra và nhịp lặp từng bảng. Sinh bởi vtcsi, sửa tay cũng được.
#
# File này CÓ vào git, khác dau-ra.yaml: hai máy dự phòng phải phát cùng một
# nhịp, nếu không thì hôm chuyển máy đầu thu thấy nhịp bảng đổi.
#
# bitrate_* là TRẦN, không phải mục tiêu. Nhịp lặp lap_* mới quyết định bảng
# ra sóng bao lâu một lần. Trần của chuẩn: ETSI TS 101 211 §4.1.
"""


def path_for(root: Path) -> Path:
    return Path(root) / FILE


def load(root: Path) -> TocDo:
    """Đọc bộ số. Thiếu file thì trả mặc định — xem docstring module."""
    p = path_for(root)
    if not p.exists():
        return TocDo()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TocDoError(f"{FILE}: không đọc được YAML ({exc})") from exc
    if data is None:
        return TocDo()
    if not isinstance(data, dict):
        raise TocDoError(f"{FILE}: nội dung phải là một khối khoá–giá trị")

    biet = {f.name for f in fields(TocDo)}
    la = sorted(set(data) - biet)
    if la:
        raise TocDoError(f"{FILE}: không hiểu khoá {', '.join(la)}")

    mac_dinh = asdict(TocDo())
    ra = {}
    for ten, cu in mac_dinh.items():
        v = data.get(ten, cu)
        if isinstance(v, bool) or not isinstance(v, int):
            raise TocDoError(f"{FILE}: {ten} phải là số nguyên, đang là {v!r}")
        ra[ten] = v
    t = TocDo(**ra)
    validate(t)
    return t


def save(t: TocDo, root: Path) -> Path:
    """Ghi bộ số. Kiểm trước khi ghi — không bao giờ để lại file không nạp được."""
    validate(t)
    p = path_for(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    than = yaml.safe_dump(asdict(t), allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    p.write_text(_HEADER + than, encoding="utf-8")
    return p
