"""Đọc và ghi ``config/dau-ra.yaml`` — vỏ có I/O.

File riêng, không nằm trong ``Config``. Lý do ở đầu ``model/output.py``: địa
chỉ đầu ra không phải báo hiệu, và nó là thứ duy nhất trong cả hệ được phép
**khác nhau giữa hai máy**.

Hệ quả thực tế của điều đó nằm ngay đây: file này **không vào git**. Cấu
hình báo hiệu vào git vì giống nhau trên cả hai máy là mục đích; địa chỉ đầu
ra mà vào git thì kéo về máy kia là hai máy cùng bắn một nhóm multicast ra
cùng một mạng — đúng cái hỏng mà cặp máy dự phòng sinh ra để tránh.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from vtcsi.model.output import Endpoint, Output, OutputError, TTL_MAC_DINH

FILE = "dau-ra.yaml"

_HEADER = """\
# Địa chỉ multicast ra headend. Sinh bởi vtcsi, sửa tay cũng được.
#
# File này KHÔNG vào git: mỗi máy một địa chỉ. Hai máy dự phòng mà cùng bắn
# một nhóm ra cùng một mạng thì hỏng đúng cái mà cặp máy sinh ra để tránh.
"""


def path_for(root: Path) -> Path:
    return Path(root) / FILE


def _endpoint(data, ten: str) -> Endpoint:
    if not isinstance(data, dict):
        raise OutputError(f"{FILE}: mục {ten!r} phải là một khối khoá–giá trị")
    cong = data.get("port", 0)
    if not isinstance(cong, int):
        raise OutputError(f"{FILE}: {ten}.port phải là số nguyên, đang là {cong!r}")
    return Endpoint(address=str(data.get("address") or "").strip(),
                    port=cong,
                    interface=str(data.get("interface") or "").strip())


def load(root: Path) -> Output:
    """Đọc cấu hình đầu ra. Chưa có file thì trả về bản rỗng.

    Không ném lỗi khi thiếu file: một máy vừa dựng chưa có đầu ra là chuyện
    bình thường, và giao diện cần mở được để người ta còn đặt vào.
    """
    p = path_for(root)
    if not p.exists():
        return Output()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise OutputError(f"{FILE}: không đọc được — {exc}") from exc
    if not isinstance(data, dict):
        raise OutputError(f"{FILE}: nội dung phải là một khối khoá–giá trị")

    ttl = data.get("ttl", TTL_MAC_DINH)
    if not isinstance(ttl, int):
        raise OutputError(f"{FILE}: ttl phải là số nguyên, đang là {ttl!r}")

    mirror = data.get("mirror")
    return Output(
        primary=_endpoint(data.get("primary") or {}, "primary"),
        mirror=_endpoint(mirror, "mirror") if mirror else None,
        ttl=ttl,
    )


def save(out: Output, root: Path) -> Path:
    """Ghi ra đĩa. Ghi qua file tạm rồi đổi tên, nên không bao giờ nửa vời."""
    p = path_for(root)
    data: dict = {
        "primary": {"address": out.primary.address,
                    "port": out.primary.port,
                    "interface": out.primary.interface},
        "ttl": out.ttl,
    }
    if out.mirror is not None and not out.mirror.empty:
        data["mirror"] = {"address": out.mirror.address,
                          "port": out.mirror.port,
                          "interface": out.mirror.interface}

    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    tam = p.with_suffix(p.suffix + ".tam")
    tam.write_text(_HEADER + body, encoding="utf-8", newline="\n")
    tam.replace(p)
    return p
