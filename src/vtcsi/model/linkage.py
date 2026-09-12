"""Luật ``linkage_descriptor`` 0x4A — lõi thuần.

Đây là phần **nguy hiểm nhất** cho phép sửa qua giao diện, vì một lý do cụ thể:
phần lớn linkage đang phát là loại *user defined* (0x80–0xFE) của Irdeto và
ViCAS, và ta **không có đặc tả** cho khối ``private_data`` của chúng. Byte
trong đó nói gì, ta không biết. Cái ta biết chắc là đầu thu Irdeto ngoài mạng
đang đọc chúng, và chúng là đường OTA nâng cấp phần mềm đầu thu.

Từ đó ra ba quy tắc của module này:

* ``private_data`` chỉ sửa được ở dạng **hex thô**, không có ô "thân thiện"
  nào. Không có đặc tả thì mọi giao diện tử tế đều là bịa.
* Độ dài khối được **hiển thị và cảnh báo khi đổi**. Sửa một byte thường vô
  hại hơn nhiều so với đổi độ dài, vì độ dài thường là thứ bên kia dùng để
  phân giải cấu trúc.
* **Thứ tự giữ nguyên**, và sửa là sửa tại chỗ theo chỉ số. Bouquet 0x3622
  đang phát hai mục ``0x80`` **giống hệt nhau** — trùng lặp có thật trên sóng.
  Khoá theo nội dung sẽ gộp chúng lại và làm đổi byte.

Đích trỏ sai thì **cảnh báo, không chặn**: sáu mục đang phát trỏ vào TSID
không tồn tại (RO-8), và cấu hình gieo từ sóng phải nạp được nguyên trạng.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from vtcsi.model.entities import Bouquet, Config, Linkage, Network

#: Bảng loại của ETSI EN 300 468 §6.2.19, Table 20. Chỉ những loại có tên.
KNOWN_TYPES: dict[int, str] = {
    0x01: "dịch vụ thông tin",
    0x02: "dịch vụ EPG",
    0x03: "dịch vụ thay thế CA",
    0x04: "TS mang đầy đủ SI của mạng hoặc bouquet",
    0x05: "dịch vụ thay thế",
    0x06: "dịch vụ quảng bá dữ liệu",
    0x07: "bảng đồ RCS",
    0x08: "chuyển giao di động",
    0x09: "dịch vụ nâng cấp phần mềm (SSU)",
    0x0A: "TS mang BAT hoặc NIT của SSU",
    0x0B: "dịch vụ thông báo IP/MAC",
    0x0C: "TS mang BAT hoặc NIT của INT",
    0x0D: "liên kết sự kiện",
}

USER_DEFINED = range(0x80, 0xFF)
"""Dải tự định nghĩa. VTC dùng 0x80, 0x82, 0x90, 0x92 cho Irdeto và ViCAS."""

MAX_PRIVATE_DATA = 248
"""Sức chứa thật của khối dữ liệu riêng, tính ra chứ không ước chừng.

``descriptor_length`` rộng một byte nên phần thân tối đa **255** byte. Thân của
``linkage_descriptor`` mở đầu bằng ``transport_stream_id`` (2) +
``original_network_id`` (2) + ``service_id`` (2) + ``linkage_type`` (1) = **7**
byte. Còn lại **248**.

Vài loại còn ăn thêm: 0x08 *chuyển giao di động* và 0x0D *liên kết sự kiện* có
trường riêng đứng trước khối này. Hai loại đó VTC không dùng, nên ta lấy trần
chung 248 và nói rõ ở đây thay vì âm thầm nới rộng.
"""


class LinkageError(ValueError):
    """Thao tác linkage bị từ chối. Thông điệp đi thẳng ra giao diện."""


def describe(linkage_type: int) -> str:
    """Tên người đọc được của một loại linkage."""
    if linkage_type in KNOWN_TYPES:
        return KNOWN_TYPES[linkage_type]
    if linkage_type in USER_DEFINED:
        return "tự định nghĩa — Irdeto hoặc ViCAS, ta không có đặc tả"
    if linkage_type == 0x00 or linkage_type == 0xFF:
        return "chuẩn dành riêng, không được dùng"
    return "chuẩn dành riêng cho tương lai"


def is_opaque(linkage_type: int) -> bool:
    """Loại này có khối ``private_data`` mà ta không giải thích được không."""
    return linkage_type in USER_DEFINED


# ------------------------------------------------------------------ hex


def parse_hex(text: str) -> bytes:
    """``"FF 04 FF"`` hoặc ``"ff04ff"`` thành byte.

    Nhận cả hai cách viết vì bản gieo dùng cách có dấu cách còn người ta hay
    dán từ nơi khác vào theo cách liền.
    """
    cleaned = "".join(text.split()).replace("-", "").replace(":", "")
    if not cleaned:
        return b""
    if len(cleaned) % 2:
        raise LinkageError(
            f"chuỗi hex lẻ số ký tự ({len(cleaned)}) — một byte cần hai ký tự")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise LinkageError(f"không phải hex: {exc}") from exc


def format_hex(data: bytes) -> str:
    """Byte thành ``"FF 04 FF"`` — đúng cách bản gieo ghi ra YAML."""
    return " ".join(f"{b:02X}" for b in data)


# ------------------------------------------------------------------ kiểm tra


@dataclass(frozen=True, slots=True)
class Problem:
    where: str
    index: int
    message: str
    blocking: bool = False

    def text(self) -> str:
        return f"{'!!' if self.blocking else ' ·'} {self.where}[{self.index}]: {self.message}"


def check(cfg: Config) -> tuple[Problem, ...]:
    """Soi mọi linkage của mạng và của mọi bouquet.

    Hai mức. **Chặn** là thứ không mã hoá nổi hoặc chuẩn cấm thẳng. **Báo** là
    đích trỏ vào chỗ không có — sai thật, nhưng sáu mục như vậy đang phát và
    ta chưa sửa (RO-8), nên chặn ở đây sẽ chặn luôn cả bản gieo.
    """
    out: list[Problem] = []
    ts_ids = {s.ts_id for s in cfg.sdts}

    def look(where: str, items: tuple[Linkage, ...]) -> None:
        for i, k in enumerate(items):
            if not 0 <= k.linkage_type <= 0xFF:
                out.append(Problem(where, i,
                                   f"loại linkage {k.linkage_type} không nằm trong một byte",
                                   blocking=True))
            elif k.linkage_type in (0x00, 0xFF):
                out.append(Problem(where, i,
                                   f"loại linkage {k.linkage_type:#04x} là giá trị chuẩn dành riêng",
                                   blocking=True))
            for name, value in (("ts_id", k.ts_id),
                                ("original_network_id", k.original_network_id),
                                ("service_id", k.service_id)):
                if not 0 <= value <= 0xFFFF:
                    out.append(Problem(where, i,
                                       f"{name} = {value} không nằm trong 16 bit",
                                       blocking=True))
            if len(k.private_data) > MAX_PRIVATE_DATA:
                out.append(Problem(where, i,
                                   f"dữ liệu riêng {len(k.private_data)} byte, "
                                   f"vượt trần {MAX_PRIVATE_DATA} của một descriptor",
                                   blocking=True))
            if k.ts_id not in ts_ids:
                out.append(Problem(
                    where, i,
                    f"trỏ tới TS {k.ts_id} không có trong cấu hình "
                    f"(đang có {sorted(ts_ids)}) — xem RO-8"))

    look("NIT", cfg.network.linkages)
    for b in cfg.bouquets:
        look(f"BAT {b.bouquet_id:04x}", b.linkages)
    return tuple(out)


def blocking(problems: tuple[Problem, ...]) -> tuple[Problem, ...]:
    return tuple(p for p in problems if p.blocking)


# ------------------------------------------------------------------ sửa đổi


def _guard(items: tuple[Linkage, ...], index: int) -> None:
    if not 0 <= index < len(items):
        raise LinkageError(
            f"không có linkage thứ {index} — đang có {len(items)} mục")


def _validate(k: Linkage) -> Linkage:
    if k.linkage_type in (0x00, 0xFF):
        raise LinkageError(
            f"loại linkage {k.linkage_type:#04x} là giá trị chuẩn dành riêng")
    if not 0 <= k.linkage_type <= 0xFF:
        raise LinkageError(f"loại linkage {k.linkage_type} không nằm trong một byte")
    for name, value in (("ts_id", k.ts_id),
                        ("original_network_id", k.original_network_id),
                        ("service_id", k.service_id)):
        if not 0 <= value <= 0xFFFF:
            raise LinkageError(f"{name} = {value} không nằm trong 16 bit")
    if len(k.private_data) > MAX_PRIVATE_DATA:
        raise LinkageError(
            f"dữ liệu riêng {len(k.private_data)} byte, vượt trần "
            f"{MAX_PRIVATE_DATA} của một descriptor")
    return k


def set_at(items: tuple[Linkage, ...], index: int, made: Linkage) -> tuple[Linkage, ...]:
    """Thay một mục **tại chỗ**, giữ nguyên thứ tự."""
    _guard(items, index)
    return items[:index] + (_validate(made),) + items[index + 1:]


def append(items: tuple[Linkage, ...], made: Linkage) -> tuple[Linkage, ...]:
    """Nối vào cuối. Không chèn giữa: thứ tự đang phát là thứ tự phải giữ."""
    return items + (_validate(made),)


def remove_at(items: tuple[Linkage, ...], index: int) -> tuple[Linkage, ...]:
    _guard(items, index)
    return items[:index] + items[index + 1:]


def on_network(net: Network, items: tuple[Linkage, ...]) -> Network:
    return replace(net, linkages=items)


def on_bouquet(bouquet: Bouquet, items: tuple[Linkage, ...]) -> Bouquet:
    return replace(bouquet, linkages=items)
