"""Kho lịch trên đĩa — vỏ có I/O.

**Bản thân thư mục file là trạng thái.** Không có cơ sở dữ liệu, không có file
trạng thái ẩn nào cạnh nó. Mỗi lần dựng cửa sổ, đọc lại tất cả file trong hộp
thư rồi gộp — nên khởi động lại là chuyện không đáng bàn, và người vận hành
nhìn thư mục là biết hệ đang có gì.

Đổi lại là đọc lại toàn bộ mỗi lần. Với 44 dịch vụ, tám ngày, mỗi ngày một
file khoảng 1 MB thì đó là chuyện của vài trăm mili giây — rẻ hơn nhiều so với
việc phải tin một kho trạng thái mà không ai soi được.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from vtcsi.epg.transform import eventid, parse, window
from vtcsi.model.entities import Event

PATTERN = "*.xml"


@dataclass(frozen=True, slots=True)
class Loaded:
    """Một file đã đọc, kèm đường dẫn để còn báo lỗi cho đúng chỗ."""

    path: Path
    ts_id: int
    original_network_id: int
    events: tuple[Event, ...]


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Kết quả dựng cửa sổ, đủ để vừa sinh bảng vừa báo động."""

    events: tuple[Event, ...]
    rejected: tuple[Event, ...]
    files: tuple[Path, ...]
    ts_id: int
    original_network_id: int

    @property
    def services(self) -> tuple[int, ...]:
        return tuple(sorted({e.service_id for e in self.events}))


class StoreError(ValueError):
    """Hộp thư không dùng được."""


def load_all(inbox: Path) -> list[Loaded]:
    """Đọc mọi file lịch trong hộp thư, theo thứ tự tên file.

    Thứ tự tên file quyết định ai ghi đè ai khi trùng khoá, nên đặt tên theo
    ngày là đủ để "bản sửa nạp sau thắng" hoạt động đúng.
    """
    if not inbox.is_dir():
        raise StoreError(f"hop thu khong ton tai: {inbox}")
    out = []
    for path in sorted(inbox.glob(PATTERN)):
        sched = parse.parse(path.read_text(encoding="utf-8"))
        out.append(Loaded(
            path=path,
            ts_id=sched.ts_id,
            original_network_id=sched.original_network_id,
            events=sched.events,
        ))
    if not out:
        raise StoreError(f"hop thu rong: {inbox}")
    return out


def build(
    inbox: Path,
    now_utc: datetime,
    depth_hours: int = window.WINDOW_HOURS,
) -> BuildResult:
    """Từ hộp thư tới tập sự kiện sẵn sàng sinh EIT.

    Bốn bước, đúng thứ tự đã lập luận ở ``window`` và ``eventid``: gộp, cắt,
    khử chồng lấn, rồi mới cấp ``event_id``. Cấp id sau cùng vì id gắn với
    thời điểm bắt đầu, mà chỉ tới lúc này mới biết sự kiện nào thật sự lên
    sóng.
    """
    loaded = load_all(inbox)

    ts_ids = {x.ts_id for x in loaded}
    if len(ts_ids) > 1:
        raise StoreError(
            "hop thu chua lich cua nhieu transport stream: "
            + ", ".join(str(t) for t in sorted(ts_ids))
            + " — moi TS mot hop thu rieng")

    merged = window.build([x.events for x in loaded], now_utc, depth_hours)
    keep, rejected = window.reject_overlong(merged)
    return BuildResult(
        events=eventid.assign_all(keep),
        rejected=rejected,
        files=tuple(x.path for x in loaded),
        ts_id=loaded[0].ts_id,
        original_network_id=loaded[0].original_network_id,
    )


def stale_files(inbox: Path, now_utc: datetime, keep_hours: int = 24) -> list[Path]:
    """File mà **mọi** sự kiện đã kết thúc từ lâu.

    Không tự xoá: trả về danh sách để người hoặc một việc định kỳ quyết định.
    Giữ thêm ``keep_hours`` sau khi hết hạn để còn truy vết được khi có sự cố.
    """
    cutoff = now_utc - timedelta(hours=keep_hours)
    out = []
    for item in load_all(inbox):
        if item.events and max(e.end_utc for e in item.events) < cutoff:
            out.append(item.path)
    return out
