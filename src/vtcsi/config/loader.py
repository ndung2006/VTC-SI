"""Đọc và ghi cấu hình YAML — vỏ có I/O.

Toàn bộ phần khó đã nằm ở ``model/plain.py`` và là hàm thuần. Ở đây chỉ còn
hai việc: chia một dict lớn ra nhiều file cho người đọc được, và ghép ngược
lại. Không có logic nghiệp vụ nào ở đây.

Bố cục trên đĩa::

    config/
      network.yaml              mạng, linkage, và tham số phát của từng TS
      services/ts8.yaml         danh sách dịch vụ của một TS
      bouquets/6510-....yaml    mỗi bouquet một file

Chia như vậy vì TSID 8 có 64 dịch vụ: nhét chung vào ``network.yaml`` thì
không ai xem diff nổi. Tên file bouquet bắt đầu bằng id dạng hex nên **sắp xếp
theo tên file cũng chính là sắp theo id** — thứ tự nạp vì thế tất định mà
không cần quy ước gì thêm.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

from vtcsi.model.entities import Config
from vtcsi.model.plain import ConfigError, from_plain, to_plain

NETWORK_FILE = "network.yaml"
SERVICES_DIR = "services"
BOUQUETS_DIR = "bouquets"

_HEADER = "# Sinh bởi vtcsi. Sửa tay thoải mái — đây là nguồn sự thật.\n"


# ------------------------------------------------------------------ tiện ích

def _slug(text: str) -> str:
    """Tên bouquet thành mẩu tên file an toàn, giữ được dấu vết gốc."""
    plain_text = unicodedata.normalize("NFKD", text)
    plain_text = "".join(c for c in plain_text if not unicodedata.combining(c))
    plain_text = re.sub(r"[^A-Za-z0-9]+", "-", plain_text).strip("-").lower()
    return plain_text or "bouquet"


def _dump(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        data,
        allow_unicode=True,   # tên kênh tiếng Việt phải đọc được, không phải \uXXXX
        sort_keys=False,      # giữ thứ tự khoá đã soạn cho người đọc
        default_flow_style=False,
        width=100,
    )
    # newline="\n" la bat buoc, khong phai chi tiet vun vat.
    #
    # Che van ban cua Python tren Windows doi \n thanh \r\n. Mot ben chay
    # Windows, mot ben chay Linux trong Docker, thi cung mot cau hinh cho ra
    # hai chuoi byte khac nhau tren dia — va "cung commit thi cung byte"
    # (§3.3 spec.md) la co che dong bo cua ca he. Git che giau duoc chuyen
    # nay khi so sanh, nen no de trot lot cho toi luc hai may thuc su phai
    # chung mot cau tra loi.
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(_HEADER + body)


def _load(path: Path):
    if not path.exists():
        raise ConfigError(f"thiếu file cấu hình: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        raise ConfigError(f"file rỗng: {path}")
    return data


# ------------------------------------------------------------------------ ghi

def save(cfg: Config, root: Path) -> list[Path]:
    """Ghi cấu hình ra đĩa. Trả về danh sách file đã ghi, theo thứ tự tất định."""
    data = to_plain(cfg)
    written: list[Path] = []

    net = data["network"]
    streams = net["transport_streams"]

    # Dịch vụ tách ra file riêng; network.yaml chỉ giữ phần khung.
    skeleton = dict(net)
    skeleton["transport_streams"] = [
        {k: v for k, v in ts.items() if k != "services"} for ts in streams
    ]
    path = root / NETWORK_FILE
    _dump({"network": skeleton}, path)
    written.append(path)

    for ts in streams:
        path = root / SERVICES_DIR / f"ts{ts['ts_id']}.yaml"
        _dump({"ts_id": ts["ts_id"], "services": ts["services"]}, path)
        written.append(path)

    for b in data["bouquets"]:
        bid = str(b["bouquet_id"]).lower().replace("0x", "")
        path = root / BOUQUETS_DIR / f"{bid}-{_slug(b['name'])}.yaml"
        _dump(b, path)
        written.append(path)

    return written


# ------------------------------------------------------------------------ đọc

def load(root: Path) -> Config:
    """Đọc cấu hình từ đĩa thành mô hình."""
    net = _load(root / NETWORK_FILE)
    if "network" not in net:
        raise ConfigError(f"{NETWORK_FILE}: thiếu khoá 'network'")
    network = net["network"]

    for ts in network.get("transport_streams", []):
        ts_id = ts.get("ts_id")
        path = root / SERVICES_DIR / f"ts{ts_id}.yaml"
        block = _load(path)
        if block.get("ts_id") != ts_id:
            raise ConfigError(
                f"{path.name}: ts_id ben trong la {block.get('ts_id')!r}, "
                f"không khớp tên file")
        ts["services"] = block.get("services", [])

    bouquet_dir = root / BOUQUETS_DIR
    bouquets = [_load(p) for p in sorted(bouquet_dir.glob("*.yaml"))] \
        if bouquet_dir.is_dir() else []

    return from_plain({"network": network, "bouquets": bouquets})
