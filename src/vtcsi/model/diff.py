"""So hai cấu hình dạng dict và chỉ đúng chỗ khác — nền của FR-43.

Điểm khiến module này đáng viết riêng thay vì dùng một thư viện diff chung:
**danh sách ở đây có khoá**. Dịch vụ định danh bằng ``service_id``, transport
stream bằng ``ts_id``, bouquet bằng ``bouquet_id``. So theo vị trí thì chèn một
kênh vào giữa sẽ hiện thành "63 dòng đổi", còn so theo khoá thì hiện đúng một
dòng "thêm kênh 845". Khác biệt giữa một bản vá đọc được và một bản vá không ai
đọc.

Hàm thuần, không đụng file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Danh sách nào định danh phần tử bằng khoá nào.
KEYS = {
    "transport_streams": "ts_id",
    "services": "service_id",
    "bouquets": "bouquet_id",
    "lcn": "service_id",
    "linkages": "linkage_type",
}


class Change(Enum):
    ADDED = "them"
    REMOVED = "bo"
    MODIFIED = "doi"


@dataclass(frozen=True, slots=True)
class Delta:
    path: str
    change: Change
    old: object = None
    new: object = None

    def line(self) -> str:
        if self.change is Change.ADDED:
            return f"  + {self.path} = {_short(self.new)}"
        if self.change is Change.REMOVED:
            return f"  - {self.path} = {_short(self.old)}"
        return f"  ~ {self.path}: {_short(self.old)} -> {_short(self.new)}"


def _short(v: object, limit: int = 60) -> str:
    text = repr(v)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _keyed(items: list, key: str) -> dict | None:
    """Danh sách thành dict theo khoá, hoặc ``None`` nếu không dùng khoá được."""
    out = {}
    for item in items:
        if not isinstance(item, dict) or key not in item:
            return None
        k = item[key]
        if k in out:
            return None          # khoa trung thi khong dinh danh duoc
        out[k] = item
    return out


def _walk(old, new, path: str, out: list[Delta]) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new), key=str):
            sub = f"{path}.{k}" if path else str(k)
            if k not in old:
                out.append(Delta(sub, Change.ADDED, new=new[k]))
            elif k not in new:
                out.append(Delta(sub, Change.REMOVED, old=old[k]))
            else:
                _walk(old[k], new[k], sub, out)
        return

    if isinstance(old, list) and isinstance(new, list):
        key = KEYS.get(path.rsplit(".", 1)[-1])
        a = _keyed(old, key) if key else None
        b = _keyed(new, key) if key else None
        if a is not None and b is not None:
            for k in sorted(set(a) | set(b), key=str):
                sub = f"{path}[{key}={k}]"
                if k not in a:
                    out.append(Delta(sub, Change.ADDED, new=b[k]))
                elif k not in b:
                    out.append(Delta(sub, Change.REMOVED, old=a[k]))
                else:
                    _walk(a[k], b[k], sub, out)
            return
        # Khong co khoa: so theo vi tri, va noi ro do la danh sach co thu tu.
        for i in range(max(len(old), len(new))):
            sub = f"{path}[{i}]"
            if i >= len(old):
                out.append(Delta(sub, Change.ADDED, new=new[i]))
            elif i >= len(new):
                out.append(Delta(sub, Change.REMOVED, old=old[i]))
            else:
                _walk(old[i], new[i], sub, out)
        return

    if old != new:
        out.append(Delta(path, Change.MODIFIED, old=old, new=new))


def diff(old: dict, new: dict) -> tuple[Delta, ...]:
    """Mọi khác biệt giữa hai cấu hình, theo thứ tự tất định."""
    out: list[Delta] = []
    _walk(old, new, "", out)
    return tuple(out)


def render(deltas: tuple[Delta, ...]) -> str:
    if not deltas:
        return "khong co khac biet"
    return "\n".join(d.line() for d in deltas)


def summarise(deltas: tuple[Delta, ...]) -> str:
    """Một dòng tóm tắt, cho nhật ký và cảnh báo."""
    if not deltas:
        return "khop"
    n = {c: sum(1 for d in deltas if d.change is c) for c in Change}
    parts = [f"{n[c]} {c.value}" for c in Change if n[c]]
    return " · ".join(parts)
