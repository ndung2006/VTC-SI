"""Dựng dòng lệnh ``tsp`` — vỏ, nhưng phần dựng là hàm thuần.

Mọi tên tuỳ chọn ở đây **tra từ tài liệu chính thống của TSDuck**, không viết
từ trí nhớ. Ba chỗ trí nhớ suýt sai:

* ``inject`` **không có** ``--interval``. Chu kỳ lặp đặt bằng cú pháp tham số
  ``tên-file=mili-giây``, còn ``--bitrate`` là bitrate của cả PID. Và bắt buộc
  đúng một trong ``--replace``, ``--bitrate``, ``--inter-packet``.
* ``eitinject`` mặc định đọc ``transport_stream_id`` **từ PAT** và mốc thời
  gian **từ TDT/TOT**. Luồng của ta không có bảng nào trong hai thứ đó, nên
  ``--ts-id`` và ``--time`` là **bắt buộc**, không phải tuỳ chọn.
* TTL multicast mặc định của hầu hết hệ điều hành là **1** — chết ngay tại
  switch đầu tiên nếu phải qua router. Tài liệu TSDuck cũng cảnh báo đúng chỗ này.

Một kết quả dễ chịu: hồ sơ chu kỳ mặc định của ``eitinject`` là hồ sơ vệ tinh
và cáp của ETSI TS 101 211 §4.4 — p/f actual 2 s, schedule prime 10 s, later
30 s, prime 8 ngày. Đúng bằng hồ sơ tuân thủ mà ``spec.md`` §7 khuyến nghị.
Nghĩa là "siết EIT schedule từ 20 s về 10 s" chỉ là **dùng mặc định**.

``build`` là hàm thuần: vào là cấu hình, ra là danh sách chuỗi. Việc chạy nó
và việc đối chiếu với ``tsp`` đã cài nằm ở ``verify``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath

PID_NIT = 16
PID_SDT_BAT = 17
PID_EIT = 18

#: Định dạng mốc thời gian của ``eitinject --time``. Không phải ISO 8601.
TIME_FORMAT = "%Y/%m/%d:%H:%M:%S"


class PipelineError(ValueError):
    """Tham số không dựng được dòng lệnh hợp lệ."""


@dataclass(frozen=True, slots=True)
class Injection:
    """Một file bảng kèm chu kỳ lặp, tính bằng mili giây."""

    path: str
    interval_ms: int

    def argument(self) -> str:
        """Cú pháp tham số của ``inject``: ``tên-file=mili-giây``."""
        if self.interval_ms <= 0:
            raise PipelineError(f"{self.path}: chu ky phai duong, gap {self.interval_ms}")
        return f"{self.path}={self.interval_ms}"


@dataclass(frozen=True, slots=True)
class Output:
    destination: str
    """``dia-chi:cong`` — tham số vị trí của ``-O ip``."""

    local_address: str | None = None
    """Card mạng phát ra. Máy nhiều card thì bắt buộc, nếu không hệ điều hành
    chọn hộ và thường chọn sai."""

    ttl: int = 8
    """Mặc định của hệ điều hành là 1, chết ngay tại switch đầu tiên."""

    packet_burst: int = 7
    """Bảy gói TS một datagram — 1316 byte, vừa một khung Ethernet thường."""

    enforce_burst: bool = True
    """Ép đúng số gói mỗi datagram. Mux đếm gói để phát hiện mất nguồn nên
    nhịp đều quan trọng hơn việc tiết kiệm vài byte."""


@dataclass(frozen=True, slots=True)
class Plan:
    """Mọi thứ cần để dựng một dòng lệnh."""

    nit: Injection
    sdt_bat: tuple[Injection, ...]
    eit_files: str
    ts_id: int
    output: Output
    bitrate_nit: int = 20_000
    bitrate_sdt_bat: int = 60_000
    bitrate_eit: int = 400_000
    """Trần bitrate từng PID. Mặc định rộng gấp mấy lần mức đo được trên sóng
    — NIT 2,9 kbps, SDT+BAT 18,8 kbps, EIT 139 kbps — vì đây là trần chứ không
    phải mục tiêu, và chật thì section bị hoãn."""

    total_bitrate: int = 2_000_000
    """Tốc độ của cả transport stream. Phần dư là null packet. Luồng phải đều
    vì mux phát hiện mất nguồn bằng cách đếm gói UDP."""

    eit_poll_ms: int = 500
    extra: tuple[str, ...] = field(default_factory=tuple)


def _pid_args(pid: int, bitrate: int, files: tuple[Injection, ...]) -> list[str]:
    if not files:
        raise PipelineError(f"PID {pid}: khong co file nao de phat")
    return (
        ["-P", "inject", "--pid", str(pid), "--bitrate", str(bitrate), "--poll-files"]
        + [f.argument() for f in files]
    )


def build(plan: Plan, *, start_time: datetime) -> list[str]:
    """Dòng lệnh đầy đủ, dạng danh sách đối số.

    ``start_time`` là mốc thời gian cho ``eitinject``; truyền vào chứ không gọi
    đồng hồ ở đây, để dựng lại được y hệt khi truy vết.
    """
    if start_time.tzinfo is None:
        raise PipelineError("start_time phai co mui gio")

    cmd: list[str] = ["tsp", "-I", "null"]
    cmd += _pid_args(PID_NIT, plan.bitrate_nit, (plan.nit,))
    cmd += _pid_args(PID_SDT_BAT, plan.bitrate_sdt_bat, plan.sdt_bat)

    cmd += [
        "-P", "eitinject",
        "--pid", str(PID_EIT),
        "--files", plan.eit_files,
        # Bat buoc: luong cua ta khong co PAT de doc ts-id, khong co TDT de lay gio.
        "--ts-id", str(plan.ts_id),
        "--time", start_time.astimezone(timezone.utc).strftime(TIME_FORMAT),
        "--actual",
        "--bitrate", str(plan.bitrate_eit),
        "--poll-interval", str(plan.eit_poll_ms),
        "--wait-first-batch",
    ]

    cmd += ["-P", "regulate", "--bitrate", str(plan.total_bitrate)]

    out = plan.output
    cmd += ["-O", "ip", "--packet-burst", str(out.packet_burst)]
    if out.enforce_burst:
        cmd += ["--enforce-burst"]
    if out.local_address:
        cmd += ["--local-address", out.local_address]
    cmd += ["--ttl", str(out.ttl), out.destination]

    return cmd + list(plan.extra)


def shell(cmd: list[str]) -> str:
    """Dòng lệnh dạng đọc được, để dán vào tài liệu vận hành."""
    def quote(a: str) -> str:
        return f"'{a}'" if (" " in a or "*" in a or "?" in a) else a
    return " ".join(quote(a) for a in cmd)


# ------------------------------------------------------- đối chiếu với tsp thật

#: Tuỳ chọn ta dùng, theo từng plugin. ``verify`` đòi ``tsp`` đã cài phải có đủ.
USED_OPTIONS = {
    "inject": ["--pid", "--bitrate", "--poll-files"],
    "eitinject": ["--pid", "--files", "--ts-id", "--time", "--actual",
                  "--bitrate", "--poll-interval", "--wait-first-batch"],
    "regulate": ["--bitrate"],
}
USED_OUTPUT_OPTIONS = {
    "ip": ["--packet-burst", "--enforce-burst", "--local-address", "--ttl"],
}


def missing_options(help_text: str, wanted: list[str]) -> list[str]:
    """Tuỳ chọn nào không thấy trong trang trợ giúp. Hàm thuần, test được."""
    return [o for o in wanted if o not in help_text]


def plan_from_config(
    *,
    build_dir: str,
    eit_dir: str,
    ts_id: int,
    other_ts_ids: tuple[int, ...],
    destination: str,
    local_address: str | None = None,
    ttl: int = 8,
    repetition_ms: dict[str, int] | None = None,
) -> Plan:
    """Kế hoạch mặc định khớp bố cục thư mục mà ``vtcsi build`` sinh ra.

    Các TS khác phải liệt kê tường minh chứ **không dùng ký tự đại diện**:
    ``sdt-ts*.xml`` sẽ khớp cả file actual, và file đó bị nạp hai lần với hai
    chu kỳ khác nhau — một lỗi im lặng, chỉ lộ ra khi đo bitrate PID 17.
    """
    rate = {"nit": 2000, "sdt_actual": 1000, "sdt_other": 5000, "bat": 5000}
    rate.update(repetition_ms or {})
    if ts_id in other_ts_ids:
        raise PipelineError(
            f"TS {ts_id} vua la actual vua nam trong danh sach other")
    b = PurePosixPath(build_dir)
    return Plan(
        nit=Injection(str(b / "nit.xml"), rate["nit"]),
        sdt_bat=(
            (Injection(str(b / f"sdt-ts{ts_id}.xml"), rate["sdt_actual"]),)
            + tuple(Injection(str(b / f"sdt-ts{t}.xml"), rate["sdt_other"])
                    for t in sorted(other_ts_ids))
            + (Injection(str(b / "bat-*.xml"), rate["bat"]),)
        ),
        eit_files=str(PurePosixPath(eit_dir) / "*.xml"),
        ts_id=ts_id,
        output=Output(destination=destination, local_address=local_address, ttl=ttl),
    )
