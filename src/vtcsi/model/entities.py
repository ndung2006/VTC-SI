"""Vật thể miền của hệ báo hiệu.

Mô hình bám **cấu trúc trên sóng**, không bám cách Barrowa tổ chức cấu hình.
Lý do: thứ ta phải tái tạo từng byte là sóng, còn cấu hình chỉ là một cách
diễn đạt nó. Cụ thể, vòng transport trong NIT và bảng SDT là hai vật thể khác
nhau dù cùng nói về một transport stream — vì trên sóng chúng đúng là vậy.

Lõi thuần: chỉ dữ liệu, không I/O, không đồng hồ. ``tests/test_purity.py``
canh chừng luật đó.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum

# ---------------------------------------------------------------- hằng số DVB


class Polarization(IntEnum):
    LINEAR_HORIZONTAL = 0
    LINEAR_VERTICAL = 1
    CIRCULAR_LEFT = 2
    CIRCULAR_RIGHT = 3


class RollOff(IntEnum):
    """Chỉ có nghĩa khi modulation_system là DVB-S2."""

    A_035 = 0
    A_025 = 1
    A_020 = 2
    RESERVED = 3


class ModulationSystem(IntEnum):
    DVB_S = 0
    DVB_S2 = 1


class ModulationType(IntEnum):
    AUTO = 0
    QPSK = 1
    PSK_8 = 2
    QAM_16 = 3


class FecInner(IntEnum):
    NOT_DEFINED = 0
    F_1_2 = 1
    F_2_3 = 2
    F_3_4 = 3
    F_5_6 = 4
    F_7_8 = 5
    F_8_9 = 6
    F_3_5 = 7
    F_4_5 = 8
    F_9_10 = 9
    NO_CONV_CODING = 15


class ServiceType(IntEnum):
    DIGITAL_TELEVISION = 0x01
    DIGITAL_RADIO_SOUND = 0x02


class RunningStatus(IntEnum):
    UNDEFINED = 0
    NOT_RUNNING = 1
    STARTS_IN_A_FEW_SECONDS = 2
    PAUSING = 3
    RUNNING = 4


# --------------------------------------------------------------- mảnh dùng chung


@dataclass(frozen=True, slots=True)
class SatelliteDelivery:
    """Tham số phát vệ tinh. Đơn vị vật lý, việc quy đổi BCD là của ``tables``."""

    frequency_hz: int
    orbital_position_deg: float
    east: bool
    polarization: Polarization
    symbol_rate_sps: int
    fec_inner: FecInner
    modulation_system: ModulationSystem = ModulationSystem.DVB_S2
    modulation_type: ModulationType = ModulationType.PSK_8
    roll_off: RollOff = RollOff.A_025


@dataclass(frozen=True, slots=True)
class Linkage:
    """``linkage_descriptor`` 0x4A.

    ``private_data`` là khối byte thô của các loại user-defined — ViCAS 0x92,
    Irdeto 0x80/0x82, SSU 0x09. Giữ nguyên byte vì ta chưa có đặc tả của chúng;
    xem RO-8 và phần Irdeto trong ``spec.md``.
    """

    linkage_type: int
    ts_id: int
    original_network_id: int
    service_id: int
    private_data: bytes = b""


@dataclass(frozen=True, slots=True)
class ServiceRef:
    """Một mục trong ``service_list_descriptor`` 0x41."""

    service_id: int
    service_type: int


@dataclass(frozen=True, slots=True)
class LcnEntry:
    """Một mục trong ``nordig_logical_channel_descriptor_v1``."""

    service_id: int
    lcn: int
    visible: bool = True


# ------------------------------------------------------------------------ NIT


@dataclass(frozen=True, slots=True)
class NitTsLoop:
    """Một vòng transport trong NIT.

    Khác ``SdtTable``: vòng này mô tả *cách thu* một TS, còn SDT mô tả *nội
    dung* của nó.
    """

    ts_id: int
    original_network_id: int
    delivery: SatelliteDelivery | None = None
    services: tuple[ServiceRef, ...] = ()
    private_data_specifier: str | int | None = None
    preferred_section: int = 0


@dataclass(frozen=True, slots=True)
class Network:
    network_id: int
    name: str
    version: int
    actual: bool = True
    linkages: tuple[Linkage, ...] = ()
    ts_loops: tuple[NitTsLoop, ...] = ()


# ------------------------------------------------------------------------ SDT


@dataclass(frozen=True, slots=True)
class Service:
    service_id: int
    name: str
    provider: str
    service_type: ServiceType
    running_status: RunningStatus = RunningStatus.RUNNING
    free_ca_mode: bool = False
    eit_pf: bool = True
    eit_schedule: bool = True


@dataclass(frozen=True, slots=True)
class SdtTable:
    ts_id: int
    original_network_id: int
    version: int
    actual: bool
    services: tuple[Service, ...] = ()


# ------------------------------------------------------------------------ BAT


@dataclass(frozen=True, slots=True)
class BatTsLoop:
    """Một vòng transport trong BAT.

    ``lcn`` nằm ở đây chứ không ở ``Service``: một kênh có mặt ở hai bouquet
    có thể mang hai số khác nhau, đúng cấu trúc BAT.
    """

    ts_id: int
    original_network_id: int
    services: tuple[ServiceRef, ...] = ()
    private_data_specifier: str | int | None = None
    lcn: tuple[LcnEntry, ...] = ()
    preferred_section: int = 0


@dataclass(frozen=True, slots=True)
class Bouquet:
    bouquet_id: int
    name: str
    version: int
    private_data_specifier: str | int | None = None
    linkages: tuple[Linkage, ...] = ()
    ts_loops: tuple[BatTsLoop, ...] = ()


# ------------------------------------------------------------------------ EPG


@dataclass(frozen=True, slots=True)
class Event:
    """Một sự kiện EPG, đã chuẩn hoá về UTC.

    ``event_id`` để trống khi vừa phân tích xong: id của nguồn không dùng được
    cho cửa sổ 8 ngày, nên ``epg.transform.eventid`` mới là chỗ cấp số thật.
    """

    service_id: int
    start_utc: datetime
    duration: timedelta
    name: str
    encoding: int
    free_ca_mode: bool = False
    running_status: RunningStatus = RunningStatus.UNDEFINED
    text: str = ""
    source_event_id: int | None = None
    event_id: int | None = None

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + self.duration


@dataclass(frozen=True, slots=True)
class Schedule:
    network_id: int
    ts_id: int
    original_network_id: int
    events: tuple[Event, ...] = ()


# ----------------------------------------------------------------- toàn cấu hình


@dataclass(frozen=True, slots=True)
class Config:
    """Toàn bộ cấu hình báo hiệu, đã nạp và kiểm tra."""

    network: Network
    sdts: tuple[SdtTable, ...] = ()
    bouquets: tuple[Bouquet, ...] = ()
