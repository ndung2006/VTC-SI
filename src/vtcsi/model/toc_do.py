"""Tốc độ dòng ra và nhịp lặp từng bảng — lõi thuần.

**Đây không phải báo hiệu DVB**, giống như địa chỉ đầu ra: không một byte nào
trong NIT, SDT, BAT hay EIT phụ thuộc vào những con số này. Nên nó nằm ngoài
``Config`` và có file riêng, đúng lý do đã ghi ở đầu ``model/output.py``.

Nhưng nó khác địa chỉ đầu ra ở một điểm quyết định, và điểm ấy định đoạt file
này vào git hay không: **hai máy phải dùng cùng bộ số**. Địa chỉ ra bắt buộc
khác nhau — hai máy không thể cùng bắn một nhóm multicast. Còn nhịp lặp mà lệch
nhau thì hôm chuyển máy, đầu thu đang quen nhận SDT mỗi giây bỗng phải chờ năm
giây, và cái đó nhìn thấy được trên màn hình khán giả. Nên ``toc-do.yaml``
**vào git**, còn ``dau-ra.yaml`` thì không.

Mọi giới hạn dưới đây lấy từ ETSI TS 101 211 §4.1, hồ sơ vệ tinh và cáp.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

#: Chu kỳ lặp **tối đa** theo ETSI TS 101 211 §4.1, tính bằng mili giây.
#:
#: Đây là trần của chuẩn, không phải khuyến nghị: vượt qua là đầu thu có thể
#: chờ quá lâu mới dựng được danh sách kênh.
TRAN_LAP = {
    "nit": 10_000,
    "sdt_actual": 2_000,
    "sdt_other": 10_000,
    "bat": 10_000,
}

#: Sàn chu kỳ lặp. Không phải luật, là hàng rào: dưới mức này thì một bảng
#: chiếm hết PID và đẩy các bảng khác ra sau, mà chẳng đầu thu nào cần nhanh
#: đến vậy.
SAN_LAP_MS = 100

#: Trần bitrate mỗi PID cho phép đặt. Rộng gấp nhiều lần nhu cầu thật; có để
#: chặn con số gõ nhầm thêm một số 0.
TRAN_PID = 5_000_000

#: Khoảng cho phép của tốc độ cả dòng.
SAN_TONG, TRAN_TONG = 100_000, 100_000_000


class TocDoError(ValueError):
    """Bộ số không dùng được. Thông điệp đi thẳng ra giao diện."""


@dataclass(frozen=True, slots=True)
class TocDo:
    """Trần bitrate từng PID, nhịp lặp từng bảng, và tốc độ cả dòng.

    Ba nhóm số này trả lời ba câu khác nhau, và lẫn chúng vào nhau là nguồn
    hiểu sai thường gặp nhất khi chỉnh:

    * ``bitrate_*`` là **trần**, không phải mục tiêu. Đặt 400 kbps không làm
      EIT chạy 400 kbps; nó chỉ nói "được phép tới đó". Đo thật trên sóng:
      NIT 2,8 · SDT+BAT 15 · EIT 191 kbps ở 43 kênh.
    * ``lap_*`` mới là thứ **quyết định** bảng ra sóng bao lâu một lần, và là
      thứ đầu thu cảm nhận được.
    * ``tong`` là tốc độ cả dòng TS. Phần dư thành gói nhồi. Nó phải đều, vì
      mux phát hiện mất nguồn bằng cách đếm gói UDP.
    """

    tong: int = 2_000_000
    bitrate_nit: int = 20_000
    bitrate_sdt_bat: int = 60_000
    bitrate_eit: int = 400_000
    lap_nit: int = 2_000
    lap_sdt_actual: int = 1_000
    lap_sdt_other: int = 5_000
    lap_bat: int = 5_000
    eit_poll_ms: int = 500

    @property
    def tong_tran_pid(self) -> int:
        """Tổng ba trần PID. So với ``tong`` để biết dòng có chở nổi không."""
        return self.bitrate_nit + self.bitrate_sdt_bat + self.bitrate_eit

    @property
    def phan_nhoi(self) -> float:
        """Tỉ lệ dòng dành cho gói nhồi, nếu cả ba PID đều chạm trần."""
        if self.tong <= 0:
            return 0.0
        return max(0.0, 1 - self.tong_tran_pid / self.tong)

    def repetition_ms(self) -> dict[str, int]:
        """Đúng khuôn ``plan_from_config`` đang nhận."""
        return {"nit": self.lap_nit, "sdt_actual": self.lap_sdt_actual,
                "sdt_other": self.lap_sdt_other, "bat": self.lap_bat}


_TEN_LAP = {
    "lap_nit": ("nit", "NIT"),
    "lap_sdt_actual": ("sdt_actual", "SDT actual"),
    "lap_sdt_other": ("sdt_other", "SDT other"),
    "lap_bat": ("bat", "BAT"),
}

_TEN_PID = {
    "bitrate_nit": "trần bitrate NIT",
    "bitrate_sdt_bat": "trần bitrate SDT+BAT",
    "bitrate_eit": "trần bitrate EIT",
}


def validate(t: TocDo) -> None:
    """Ném ``TocDoError`` ở con số đầu tiên không dùng được.

    Chặn chứ không cảnh báo, vì cả bốn nhóm lỗi dưới đây đều là thứ không thể
    đúng trong bất kỳ hoàn cảnh nào — khác với những chỗ ``canh_bao`` xử lý,
    vốn là đánh đổi tuỳ hoàn cảnh.
    """
    for truong, (khoa, ten) in _TEN_LAP.items():
        v = getattr(t, truong)
        if not isinstance(v, int) or v < SAN_LAP_MS:
            raise TocDoError(
                f"nhịp lặp {ten} phải là số nguyên từ {SAN_LAP_MS} ms trở lên, "
                f"đang là {v!r}")
        if v > TRAN_LAP[khoa]:
            raise TocDoError(
                f"nhịp lặp {ten} là {v} ms, vượt trần {TRAN_LAP[khoa]} ms của "
                f"ETSI TS 101 211 — đầu thu có thể chờ quá lâu mới dựng được "
                f"danh sách kênh")

    for truong, ten in _TEN_PID.items():
        v = getattr(t, truong)
        if not isinstance(v, int) or not 0 < v <= TRAN_PID:
            raise TocDoError(f"{ten} phải là số nguyên trong khoảng "
                             f"1–{TRAN_PID} bit/s, đang là {v!r}")

    if not isinstance(t.tong, int) or not SAN_TONG <= t.tong <= TRAN_TONG:
        raise TocDoError(f"tốc độ cả dòng phải trong khoảng "
                         f"{SAN_TONG}–{TRAN_TONG} bit/s, đang là {t.tong!r}")

    if not isinstance(t.eit_poll_ms, int) or not 50 <= t.eit_poll_ms <= 60_000:
        raise TocDoError(f"nhịp ngó lại file EIT phải từ 50 đến 60000 ms, "
                         f"đang là {t.eit_poll_ms!r}")


#: Bộ số **khuyến nghị**, và cũng là mặc định. Một, không phải hai.
#:
#: Không tách làm hai hằng số, và đó là chủ ý. Một bộ "mặc định" khác bộ
#: "khuyến nghị" nghĩa là hệ tự khởi động bằng thứ chính mình bảo đừng dùng —
#: và rồi phải giải thích với người vận hành vì sao. Bộ này đã chạy trên sóng
#: thật và đo được: nhịp lặp nằm trong trần ETSI TS 101 211 với biên rộng, ba
#: trần bitrate đều cao hơn mức đo được ít nhất 1,7 lần.
KHUYEN_NGHI = TocDo()


def khac_khuyen_nghi(t: TocDo) -> tuple[str, ...]:
    """Tên những trường đang lệch khỏi bộ khuyến nghị, đã sắp thứ tự."""
    return tuple(sorted(
        f.name for f in fields(TocDo)
        if getattr(t, f.name) != getattr(KHUYEN_NGHI, f.name)))


def so(n: int) -> str:
    """``2000000`` thành ``2.000.000``.

    Định dạng riêng từng số chứ **không** ``.replace(",", ".")`` lên cả câu:
    làm vậy thì dấu phẩy của chính câu văn cũng thành dấu chấm, và câu đứt
    làm đôi giữa chừng. Đã lỡ một lần.
    """
    return f"{n:,}".replace(",", ".")


def canh_bao(t: TocDo) -> tuple[str, ...]:
    """Những chỗ hợp lệ nhưng đáng nghĩ lại. Báo ra, không chặn."""
    ra: list[str] = []

    if t.tong_tran_pid > t.tong:
        ra.append(
            f"Tổng ba trần PID là {so(t.tong_tran_pid)} bit/s, lớn hơn tốc độ "
            f"cả dòng {so(t.tong)}. Ba PID không thể cùng chạm trần; khi dữ "
            f"liệu nhiều lên thì section bị hoãn, và triệu chứng trông y hệt "
            f"mất kênh.")

    # Ngưỡng lấy từ số liệu ĐO THẬT trên sóng, không phải ước lượng.
    for truong, ten, do_duoc in (("bitrate_nit", "NIT", 3_000),
                                 ("bitrate_sdt_bat", "SDT+BAT", 20_000),
                                 ("bitrate_eit", "EIT", 240_000)):
        v = getattr(t, truong)
        if v < do_duoc:
            ra.append(
                f"Trần {ten} là {so(v)} bit/s, thấp hơn mức đã đo được trên "
                f"sóng ({so(do_duoc)} bit/s). Chật thì section bị hoãn.")

    if t.lap_sdt_actual > TRAN_LAP["sdt_actual"] // 2:
        ra.append(
            f"SDT actual lặp mỗi {t.lap_sdt_actual} ms, sát trần "
            f"{TRAN_LAP['sdt_actual']} ms của chuẩn. Còn ít biên khi dòng bận.")

    return tuple(ra)
