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

    mirror: str | None = None
    """``dia-chi:cong`` của đường sao chép, hoặc ``None``."""

    mirror_local_address: str | None = None
    """Card mạng cho đường sao chép. Thường là card KHÁC — đó mới là lý do
    có đường thứ hai."""

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

    # `--bitrate` o muc tsp, TRUOC moi plugin.
    #
    # `-I null` khong khai bitrate nao ca, va `inject` can biet bitrate cua
    # dong de tinh khoang cach goi. Neu chi dua bitrate cho `regulate` — nam
    # CUOI chuoi — thi `inject` van khong biet gi, va `tsp` chet ngay khi khoi
    # dong:
    #
    #     Error: inject: input bitrate unknown or too low, specify --inter-packet
    #
    # Lan chay toan trinh dau tien bat duoc. Truoc do lenh nay chua bao gio
    # duoc chay that — no chi duoc so chuoi trong cac bai kiem.
    cmd: list[str] = ["tsp", "--bitrate", str(plan.total_bitrate), "-I", "null"]
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
        # Ep mot bang ma duy nhat cho ten su kien.
        #
        # Khong dat thi TSDuck chon bang ma **cho tung chuoi**, lay cai gon
        # nhat ma chuoi do vua: phan lon ra 0x15 UTF-8, nhung mot so ten lai
        # ra ISO-8859-15 (0x0B) hoac ISO-8859-2 (0x10 0x0002). Ca hai deu hop
        # chuan va giai dung — nhung lan chay toan trinh dau tien, khi do byte
        # voi ban thu song that, cho thay Barrowa **chua bao gio** phat hai
        # bang ma do: no chi dung 0x15 khi co dau va de tran khi thuan ASCII.
        #
        # Day la he du phong cho Barrowa, nen tieu chuan la nhung gi Barrowa
        # dang lam. Dua len song mot bang ma ma ca dan dau thu chua tung gap
        # la mot rui ro khong can thiet, va la kieu chi lo ra o nha khan gia.
        #
        # SDT va BAT khong can tuy chon nay: ten dich vu va ten bouquet deu
        # thuan ASCII nen da de tran, trung khop tung byte voi song that.
        "--default-charset", "UTF-8",
        "--bitrate", str(plan.bitrate_eit),
        "--poll-interval", str(plan.eit_poll_ms),
        "--wait-first-batch",
        # Giu chuong trinh da phat xong cho het phan doan ba gio dang chay.
        #
        # Mac dinh `eitinject` GO NGAY mot su kien vua ket thuc. Do la ly do
        # bang ta sinh ra bat dau tu 00:00 UTC (FR-98) ma tren song lai bat dau
        # tu 06:45 — do la chuong trinh dang chay luc thu. Ta nap du ca ngay,
        # `eitinject` loc lai.
        #
        # Co nay dua duoc toi mep phan doan (06:00), khong toi duoc dau ngay.
        # Barrowa giu ca ngay tu 00:00; TSDuck khong co cach nao lam vay, va
        # day la muc gan nhat dat duoc. Xem FR-99.
        "--lazy-schedule-update",
    ]

    cmd += ["-P", "regulate", "--bitrate", str(plan.total_bitrate)]

    out = plan.output

    # Đường sao chép: một `tsp` con, nhận dòng qua ống.
    #
    # `-O ip` chỉ nhận MỘT đích, và `tsp` chỉ có một plugin đầu ra. Nên bản
    # sao phải là một tiến trình riêng: `fork` đẩy y nguyên dòng gói sang
    # stdin của nó, và nó tự bắn ra nhóm thứ hai.
    #
    # Đặt TRƯỚC `-O ip` là cố ý: `fork` là một plugin xử lý, nó phải nằm
    # trong chuỗi. Đặt sau thì không còn chỗ nào để đặt.
    #
    # Nhánh con KHÔNG có `regulate`: nhịp đã do nhánh cha giữ, và hai bộ
    # điều nhịp trên cùng một dòng thì đánh nhau.
    if out.mirror:
        con = ["tsp", "-I", "file", "-", "-O", "ip",
               "--packet-burst", str(out.packet_burst)]
        if out.enforce_burst:
            con += ["--enforce-burst"]
        if out.mirror_local_address:
            con += ["--local-address", out.mirror_local_address]
        con += ["--ttl", str(out.ttl), out.mirror]
        cmd += ["-P", "fork", shell(con)]

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
                  "--default-charset", "--bitrate", "--poll-interval",
                  "--wait-first-batch", "--lazy-schedule-update"],
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
    bouquet_ids: tuple[int, ...],
    destination: str,
    local_address: str | None = None,
    mirror: str | None = None,
    mirror_local_address: str | None = None,
    ttl: int = 8,
    repetition_ms: dict[str, int] | None = None,
    bitrates: dict[str, int] | None = None,
) -> Plan:
    """Kế hoạch mặc định khớp bố cục thư mục mà ``vtcsi build`` sinh ra.

    **Không một đường dẫn nào ở tuyến ``inject`` được mang ký tự đại diện.**
    Hai lý do khác nhau, và cả hai đều hỏng lặng lẽ:

    * ``sdt-ts*.xml`` khớp cả file actual, nên file đó bị nạp hai lần với hai
      chu kỳ khác nhau — chỉ lộ ra khi đo bitrate PID 17.
    * ``bat-*.xml`` thì tệ hơn: plugin ``inject`` của TSDuck **không nở ký tự
      đại diện**. Nó nhận nguyên chuỗi ``bat-*.xml`` làm tên file, không tìm
      thấy, và **không báo lỗi**. ``tsp`` chạy bình thường, PID 17 vẫn có
      bitrate, NIT và SDT vẫn lên sóng — chỉ toàn bộ BAT là biến mất. Lần chạy
      toàn trình đầu tiên bắt được đúng chỗ này.

    ``eitinject --files`` thì ngược lại, **có** nở ký tự đại diện; đó là lý do
    ``eit_files`` vẫn giữ ``*.xml``. Hai plugin, hai luật — nên phải ghi ra.
    """
    rate = {"nit": 2000, "sdt_actual": 1000, "sdt_other": 5000, "bat": 5000}
    rate.update(repetition_ms or {})
    if ts_id in other_ts_ids:
        raise PipelineError(
            f"TS {ts_id} vua la actual vua nam trong danh sach other")
    # Chuan hoa dau phan cach truoc khi ghep.
    #
    # `PurePosixPath` coi mot duong dan Windows la MOT doan, nen ghep xong ra
    # `C:\\build\\eit/*.xml` — tron hai kieu. Tren Linux thi khong xay ra,
    # nhung dong lenh in ra de doc va de dan la mot phan cua cong cu, va mot
    # dong lenh trong tai lieu van hanh ma dan vao khong chay duoc thi te hon
    # la khong co.
    b = PurePosixPath(str(build_dir).replace(chr(92), "/"))
    return Plan(
        nit=Injection(str(b / "nit.xml"), rate["nit"]),
        sdt_bat=(
            (Injection(str(b / f"sdt-ts{ts_id}.xml"), rate["sdt_actual"]),)
            + tuple(Injection(str(b / f"sdt-ts{t}.xml"), rate["sdt_other"])
                    for t in sorted(other_ts_ids))
            + tuple(Injection(str(b / f"bat-{q:04x}.xml"), rate["bat"])
                    for q in sorted(bouquet_ids))
        ),
        eit_files=str(PurePosixPath(str(eit_dir).replace(chr(92), "/")) / "*.xml"),
        ts_id=ts_id,
        output=Output(destination=destination, local_address=local_address,
                      mirror=mirror, mirror_local_address=mirror_local_address,
                      ttl=ttl),
        # Thieu khoa nao thi giu mac dinh cua `Plan`, khong doan.
        **{k: v for k, v in (bitrates or {}).items()
           if k in ("bitrate_nit", "bitrate_sdt_bat", "bitrate_eit",
                    "total_bitrate", "eit_poll_ms")},
    )
