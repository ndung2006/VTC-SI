"""Địa chỉ multicast đầu ra — lõi thuần.

**Đây không phải báo hiệu DVB.** Không một byte nào trong NIT, SDT, BAT hay
EIT phụ thuộc vào địa chỉ này; nó chỉ nói dòng TS chảy ra cổng mạng nào để
tới headend. Vì thế nó nằm ngoài ``Config`` và có file riêng: kéo nó vào
``Config`` là kéo nó vào ``to_plain``/``from_plain`` và vào cả bộ so byte,
nơi nó không có việc gì để làm.

Ranh giới đó còn có mặt thứ hai, quan trọng hơn: cấu hình báo hiệu giống
nhau trên cả hai máy — đó là cơ chế đồng bộ. Còn địa chỉ đầu ra thì **phải
khác nhau**: hai máy không thể cùng bắn một nhóm multicast ra cùng một
mạng. Nên nó là thứ duy nhất trong cả hệ có quyền lệch giữa hai máy, và để
riêng ra là cách nói điều đó thành cấu trúc.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TTL_MAC_DINH = 8
CONG_TOI_DA = 65535


class OutputError(ValueError):
    """Địa chỉ đầu ra không dùng được. Thông điệp đi thẳng ra giao diện."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Một đường ra: bắn tới ``address:port``, đi qua card ``interface``."""

    address: str = ""
    port: int = 0
    interface: str = ""
    """Địa chỉ IP của card mạng dùng để phát. Bỏ trống thì hệ điều hành tự
    chọn theo bảng định tuyến — xem ``warnings``: trên máy có nhiều giao diện
    mạng, kết quả không xác định."""

    @property
    def empty(self) -> bool:
        return not self.address.strip() and not self.port


@dataclass(frozen=True, slots=True)
class Output:
    """Đầu ra của hệ: một đường chính, và tuỳ chọn một đường sao chép."""

    primary: Endpoint = field(default_factory=Endpoint)
    mirror: Endpoint | None = None
    ttl: int = TTL_MAC_DINH


# ------------------------------------------------------------------ đọc số

def parse_ip(text: str) -> tuple[int, int, int, int]:
    """Chuỗi thành bốn số. Ném ``OutputError`` kèm lý do đọc được."""
    raw = (text or "").strip()
    if not raw:
        raise OutputError("để trống")
    parts = raw.split(".")
    if len(parts) != 4:
        raise OutputError(f"{raw!r} không đúng định dạng IPv4: cần bốn nhóm số "
                          "phân cách bằng dấu chấm")
    out = []
    for p in parts:
        if not p.isdigit() or (len(p) > 1 and p[0] == "0"):
            raise OutputError(f"{raw!r}: nhóm {p!r} không phải số hợp lệ")
        n = int(p)
        if n > 255:
            raise OutputError(f"{raw!r}: giá trị {n} vượt giới hạn 255 của một octet")
        out.append(n)
    return tuple(out)  # type: ignore[return-value]


def valid_ip(text: str) -> bool:
    try:
        parse_ip(text)
    except OutputError:
        return False
    return True


def is_multicast(text: str) -> bool:
    """224.0.0.0 – 239.255.255.255, theo RFC 5771."""
    try:
        a = parse_ip(text)[0]
    except OutputError:
        return False
    return 224 <= a <= 239


def format_endpoint(e: Endpoint) -> str:
    return f"{e.address.strip()}:{e.port}"


def same_wire(a: Endpoint, b: Endpoint) -> bool:
    """Hai đường có đi ra **cùng một card** không."""
    return a.interface.strip() == b.interface.strip()


# ------------------------------------------------------------- luật chặn

def _check_endpoint(e: Endpoint, ten: str) -> list[str]:
    ra: list[str] = []
    try:
        parse_ip(e.address)
    except OutputError as exc:
        ra.append(f"{ten}: địa chỉ đích {exc}")
    if not 1 <= e.port <= CONG_TOI_DA:
        ra.append(f"{ten}: cổng {e.port} nằm ngoài khoảng hợp lệ "
                  f"1–{CONG_TOI_DA}")
    if e.interface.strip():
        try:
            parse_ip(e.interface)
        except OutputError as exc:
            ra.append(f"{ten}: địa chỉ card mạng {exc}")
    return ra


def check(out: Output) -> tuple[str, ...]:
    """Những gì **chặn** phát sóng. Rỗng nghĩa là dùng được."""
    ra = _check_endpoint(out.primary, "Đường chính")

    if not 1 <= out.ttl <= 255:
        ra.append(f"TTL {out.ttl} nằm ngoài khoảng hợp lệ 1–255")

    if out.mirror is not None and not out.mirror.empty:
        ra += _check_endpoint(out.mirror, "Đường sao chép")
        trung_dia_chi = (out.mirror.address.strip() == out.primary.address.strip()
                         and out.mirror.port == out.primary.port)
        if trung_dia_chi and same_wire(out.mirror, out.primary):
            ra.append(
                "Đường sao chép trùng hoàn toàn đường chính: cùng địa chỉ "
                "nhóm, cùng cổng, cùng card mạng. Cấu hình này phát mỗi gói "
                "hai lần trên cùng một giao diện; thiết bị đầu xa sẽ nhận gói "
                "trùng lặp và bản tin lỗi, chứ không có thêm đường dự phòng "
                "nào. Cần đổi card mạng phát hoặc chọn địa chỉ nhóm khác.")
    return tuple(ra)


def blocking(out: Output) -> bool:
    return bool(check(out))


# --------------------------------------------------------- lời nhắc, không chặn

def warnings(out: Output) -> tuple[str, ...]:
    """Những gì **đáng ngờ** nhưng vẫn chạy được."""
    ra: list[str] = []

    if out.primary.address.strip() and not is_multicast(out.primary.address):
        ra.append(
            f"{out.primary.address} không thuộc dải địa chỉ multicast "
            "(224.0.0.0 – 239.255.255.255). Phát đơn hướng tới một máy đích "
            "vẫn hoạt động, nhưng thiết bị tại trung tâm phát sóng thường thu "
            "theo nhóm multicast. Đề nghị kiểm tra lại địa chỉ.")

    if not out.primary.interface.strip():
        ra.append(
            "Đường chính chưa chỉ định card mạng phát; hệ điều hành sẽ tự "
            "chọn theo bảng định tuyến. Trên máy có nhiều giao diện mạng, kết "
            "quả không xác định và có thể thay đổi sau mỗi lần điều chỉnh hạ "
            "tầng mạng, mà không phát sinh cảnh báo nào.")

    if out.ttl == 1:
        ra.append(
            "TTL 1 giới hạn gói trong phạm vi một phân đoạn mạng: gói không "
            "vượt qua được bộ định tuyến nào. Chỉ phù hợp khi thiết bị thu nằm "
            "cùng miền quảng bá với máy này.")

    if out.mirror is None or out.mirror.empty:
        ra.append(
            "Chưa cấu hình đường sao chép. Hệ hiện chỉ có một đường phát: sự "
            "cố trên card mạng đó sẽ làm gián đoạn toàn bộ báo hiệu, trong khi "
            "tiến trình vẫn hoạt động bình thường và không phát cảnh báo.")
    elif same_wire(out.mirror, out.primary):
        ra.append(
            "Hai đường phát dùng chung một card mạng. Địa chỉ nhóm khác "
            "nhau, nhưng sự cố phần cứng trên card sẽ làm mất đồng thời cả hai "
            "đường; cấu hình này chưa cấu thành dự phòng đường truyền.")

    return tuple(ra)
