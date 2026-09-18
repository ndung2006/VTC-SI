"""Cầu nối với lược đồ XML của TSDuck — đọc, ghi, và so sánh chuẩn hoá.

Ba việc, cùng một chỗ vì chúng dùng chung bộ quy ước về kiểu dữ liệu:

* ``read`` — bản dump ``tstables --xml-output`` thành mô hình. Đây là cách
  **gieo cấu hình** cho hệ mới: 88 dịch vụ, 87 LCN, 136 mục service list đều
  lấy thẳng từ sóng, không gõ tay.
* ``write_*`` — mô hình thành ``Element`` cho TSDuck sinh bảng.
* ``canon`` — dạng chuẩn hoá để so hai cây XML theo *giá trị*, bỏ qua khác
  biệt cách viết. Cần vì ``0x0008``, ``8`` và ``11,088,000,000`` với
  ``11088000000`` là cùng một thứ.

Hàm thuần: vào là chuỗi hoặc mô hình, ra là mô hình hoặc ``Element``.
Chỉ dùng ``ET.fromstring``; không bao giờ ``ET.parse`` vì hàm đó chạm I/O.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from vtcsi.model.entities import (
    BatTsLoop,
    Bouquet,
    Config,
    FecInner,
    LcnEntry,
    Linkage,
    ModulationSystem,
    ModulationType,
    Network,
    NitTsLoop,
    Polarization,
    RollOff,
    RunningStatus,
    SatelliteDelivery,
    SdtTable,
    Service,
    ServiceRef,
    ServiceType,
)

LCN_DESCRIPTOR = "nordig_logical_channel_descriptor_v1"
"""Biến thể LCN đang phát sóng — đo trên luồng thật, không phải PDS 0x31 như
tên tham số ``lcn_priv_spec`` của Barrowa gợi ý."""


class TsduckError(ValueError):
    """Lược đồ không như mong đợi. Luôn nói rõ chỗ sai."""


# --------------------------------------------------------------- quy đổi kiểu

_POL = {"horizontal": Polarization.LINEAR_HORIZONTAL, "vertical": Polarization.LINEAR_VERTICAL,
        "left": Polarization.CIRCULAR_LEFT, "right": Polarization.CIRCULAR_RIGHT}
_ROLL = {"0.35": RollOff.A_035, "0.25": RollOff.A_025, "0.20": RollOff.A_020}
_SYS = {"DVB-S": ModulationSystem.DVB_S, "DVB-S2": ModulationSystem.DVB_S2}
_MOD = {"auto": ModulationType.AUTO, "QPSK": ModulationType.QPSK,
        "8PSK": ModulationType.PSK_8, "16-QAM": ModulationType.QAM_16}
_FEC = {"1/2": FecInner.F_1_2, "2/3": FecInner.F_2_3, "3/4": FecInner.F_3_4,
        "5/6": FecInner.F_5_6, "7/8": FecInner.F_7_8, "8/9": FecInner.F_8_9,
        "3/5": FecInner.F_3_5, "4/5": FecInner.F_4_5, "9/10": FecInner.F_9_10}
_RUN = {"undefined": RunningStatus.UNDEFINED, "not-running": RunningStatus.NOT_RUNNING,
        "starting": RunningStatus.STARTS_IN_A_FEW_SECONDS, "pausing": RunningStatus.PAUSING,
        "running": RunningStatus.RUNNING}

_POL_OUT = {v: k for k, v in _POL.items()}
_ROLL_OUT = {v: k for k, v in _ROLL.items()}
_SYS_OUT = {v: k for k, v in _SYS.items()}
_MOD_OUT = {v: k for k, v in _MOD.items()}
_FEC_OUT = {v: k for k, v in _FEC.items()}
_RUN_OUT = {v: k for k, v in _RUN.items()}


def num(text: str) -> int:
    """``0x0008``, ``8`` hay ``11,088,000,000`` đều ra số nguyên."""
    t = text.strip().replace(",", "").replace(" ", "")
    return int(t, 16) if t.lower().startswith("0x") else int(t)


def _flag(text: str | None, default: bool = False) -> bool:
    if text is None:
        return default
    return text.strip().lower() == "true"


def _hex_bytes(text: str | None) -> bytes:
    if not text or not text.strip():
        return b""
    return bytes.fromhex(text.replace("\n", " ").replace(" ", ""))


def _pds(text: str | None) -> str | int | None:
    """PDS có thể là tên (``NorDig``) hoặc số (``0x00362275``).

    Giữ nguyên dạng nguồn: TSDuck nhận cả hai khi đọc, và tên thì mang nhiều
    thông tin hơn cho người đọc cấu hình.
    """
    if text is None:
        return None
    t = text.strip()
    try:
        return num(t)
    except ValueError:
        return t


def _lookup(table: dict, key: str, what: str):
    if key not in table:
        raise TsduckError(f"{what} khong nhan dang duoc: {key!r}")
    return table[key]


# ------------------------------------------------------------------ ĐỌC


def _read_linkage(el: ET.Element) -> Linkage:
    pd = el.find("private_data")
    return Linkage(
        linkage_type=num(el.get("linkage_type", "0")),
        ts_id=num(el.get("transport_stream_id", "0")),
        original_network_id=num(el.get("original_network_id", "0")),
        service_id=num(el.get("service_id", "0")),
        private_data=_hex_bytes(pd.text if pd is not None else None),
    )


def _read_service_list(el: ET.Element | None) -> tuple[ServiceRef, ...]:
    if el is None:
        return ()
    return tuple(
        ServiceRef(num(s.get("service_id")), num(s.get("service_type")))
        for s in el.findall("service")
    )


def _read_delivery(el: ET.Element) -> SatelliteDelivery:
    return SatelliteDelivery(
        frequency_hz=num(el.get("frequency")),
        orbital_position_deg=float(el.get("orbital_position")),
        east=el.get("west_east_flag", "east") == "east",
        polarization=_lookup(_POL, el.get("polarization"), "polarization"),
        symbol_rate_sps=num(el.get("symbol_rate")),
        fec_inner=_lookup(_FEC, el.get("FEC_inner"), "FEC_inner"),
        modulation_system=_lookup(_SYS, el.get("modulation_system", "DVB-S2"), "modulation_system"),
        modulation_type=_lookup(_MOD, el.get("modulation_type", "8PSK"), "modulation_type"),
        roll_off=_lookup(_ROLL, el.get("roll_off", "0.25"), "roll_off"),
    )


def read_nit(el: ET.Element) -> Network:
    dsd = el.find("network_name_descriptor")
    loops = []
    for ts in el.findall("transport_stream"):
        deliv = ts.find("satellite_delivery_system_descriptor")
        loops.append(
            NitTsLoop(
                ts_id=num(ts.get("transport_stream_id")),
                original_network_id=num(ts.get("original_network_id")),
                delivery=_read_delivery(deliv) if deliv is not None else None,
                services=_read_service_list(ts.find("service_list_descriptor")),
                private_data_specifier=_pds(
                    ts.find("private_data_specifier_descriptor").get("private_data_specifier")
                    if ts.find("private_data_specifier_descriptor") is not None
                    else None
                ),
                preferred_section=int(ts.get("preferred_section", "0")),
            )
        )
    return Network(
        network_id=num(el.get("network_id")),
        name=dsd.get("network_name") if dsd is not None else "",
        version=int(el.get("version", "0")),
        actual=_flag(el.get("actual"), True),
        linkages=tuple(_read_linkage(x) for x in el.findall("linkage_descriptor")),
        ts_loops=tuple(loops),
    )


def read_sdt(el: ET.Element) -> SdtTable:
    services = []
    for s in el.findall("service"):
        d = s.find("service_descriptor")
        if d is None:
            raise TsduckError(f"dich vu {s.get('service_id')} thieu service_descriptor")
        services.append(
            Service(
                service_id=num(s.get("service_id")),
                name=d.get("service_name", ""),
                provider=d.get("service_provider_name", ""),
                service_type=ServiceType(num(d.get("service_type"))),
                running_status=_lookup(_RUN, s.get("running_status", "undefined"), "running_status"),
                free_ca_mode=_flag(s.get("CA_mode")),
                eit_pf=_flag(s.get("EIT_present_following")),
                eit_schedule=_flag(s.get("EIT_schedule")),
            )
        )
    return SdtTable(
        ts_id=num(el.get("transport_stream_id")),
        original_network_id=num(el.get("original_network_id")),
        version=int(el.get("version", "0")),
        actual=_flag(el.get("actual"), True),
        services=tuple(services),
    )


def read_bat(el: ET.Element) -> Bouquet:
    name = el.find("bouquet_name_descriptor")
    top_pds = el.find("private_data_specifier_descriptor")
    loops = []
    for ts in el.findall("transport_stream"):
        lcn_el = ts.find(LCN_DESCRIPTOR)
        pds_el = ts.find("private_data_specifier_descriptor")
        loops.append(
            BatTsLoop(
                ts_id=num(ts.get("transport_stream_id")),
                original_network_id=num(ts.get("original_network_id")),
                services=_read_service_list(ts.find("service_list_descriptor")),
                private_data_specifier=_pds(
                    pds_el.get("private_data_specifier") if pds_el is not None else None
                ),
                lcn=tuple(
                    LcnEntry(
                        service_id=num(s.get("service_id")),
                        lcn=int(s.get("logical_channel_number")),
                        visible=_flag(s.get("visible_service"), True),
                    )
                    for s in (lcn_el.findall("service") if lcn_el is not None else [])
                ),
                preferred_section=int(ts.get("preferred_section", "0")),
            )
        )
    return Bouquet(
        bouquet_id=num(el.get("bouquet_id")),
        name=name.get("bouquet_name") if name is not None else "",
        version=int(el.get("version", "0")),
        private_data_specifier=_pds(
            top_pds.get("private_data_specifier") if top_pds is not None else None
        ),
        linkages=tuple(_read_linkage(x) for x in el.findall("linkage_descriptor")),
        ts_loops=tuple(loops),
    )


def read_dump(xml_text: str) -> Config:
    """Bản dump ``tstables --xml-output`` thành ``Config``.

    Bỏ qua mọi bảng không phải NIT/SDT/BAT — bản dump đầu ra mux còn lẫn PAT,
    PMT, CAT và hàng vạn bảng ECM.
    """
    root = ET.fromstring(xml_text)
    if root.tag != "tsduck":
        raise TsduckError(f"the goc phai la <tsduck>, gap <{root.tag}>")

    nets = [read_nit(x) for x in root.findall("NIT")]
    if len(nets) != 1:
        raise TsduckError(f"can dung mot NIT, tim thay {len(nets)}")

    sdts = sorted((read_sdt(x) for x in root.findall("SDT")), key=lambda s: s.ts_id)
    bouquets = sorted((read_bat(x) for x in root.findall("BAT")), key=lambda b: b.bouquet_id)
    return Config(network=nets[0], sdts=tuple(sdts), bouquets=tuple(bouquets))


# ------------------------------------------------------------------ GHI


def _hex16(v: int) -> str:
    return "0x%04X" % v


def _put_linkage(parent: ET.Element, lk: Linkage) -> None:
    el = ET.SubElement(parent, "linkage_descriptor", {
        "transport_stream_id": _hex16(lk.ts_id),
        "original_network_id": _hex16(lk.original_network_id),
        "service_id": _hex16(lk.service_id),
        "linkage_type": "0x%02X" % lk.linkage_type,
    })
    if lk.private_data:
        ET.SubElement(el, "private_data").text = " ".join("%02X" % b for b in lk.private_data)


def _put_service_list(parent: ET.Element, refs: tuple[ServiceRef, ...]) -> None:
    if not refs:
        return
    el = ET.SubElement(parent, "service_list_descriptor")
    for r in refs:
        ET.SubElement(el, "service", {
            "service_id": _hex16(r.service_id),
            "service_type": "0x%02X" % r.service_type,
        })


def _put_pds(parent: ET.Element, pds: str | int | None) -> None:
    if pds is None:
        return
    value = pds if isinstance(pds, str) else "0x%08X" % pds
    ET.SubElement(parent, "private_data_specifier_descriptor",
                  {"private_data_specifier": value})


def write_nit(net: Network) -> ET.Element:
    el = ET.Element("NIT", {
        "version": str(net.version),
        "current": "true",
        "network_id": _hex16(net.network_id),
        "actual": "true" if net.actual else "false",
    })
    ET.SubElement(el, "network_name_descriptor", {"network_name": net.name})
    for lk in net.linkages:
        _put_linkage(el, lk)
    for loop in net.ts_loops:
        ts = ET.SubElement(el, "transport_stream", {
            "transport_stream_id": _hex16(loop.ts_id),
            "original_network_id": _hex16(loop.original_network_id),
            "preferred_section": str(loop.preferred_section),
        })
        if loop.delivery is not None:
            d = loop.delivery
            ET.SubElement(ts, "satellite_delivery_system_descriptor", {
                "frequency": str(d.frequency_hz),
                "orbital_position": "%.1f" % d.orbital_position_deg,
                "west_east_flag": "east" if d.east else "west",
                "polarization": _POL_OUT[d.polarization],
                "roll_off": _ROLL_OUT[d.roll_off],
                "modulation_system": _SYS_OUT[d.modulation_system],
                "modulation_type": _MOD_OUT[d.modulation_type],
                "symbol_rate": str(d.symbol_rate_sps),
                "FEC_inner": _FEC_OUT[d.fec_inner],
            })
        _put_service_list(ts, loop.services)
        _put_pds(ts, loop.private_data_specifier)
    return el


def write_sdt(sdt: SdtTable) -> ET.Element:
    el = ET.Element("SDT", {
        "version": str(sdt.version),
        "current": "true",
        "transport_stream_id": _hex16(sdt.ts_id),
        "original_network_id": _hex16(sdt.original_network_id),
        "actual": "true" if sdt.actual else "false",
    })
    for s in sdt.services:
        sv = ET.SubElement(el, "service", {
            "service_id": _hex16(s.service_id),
            "EIT_schedule": "true" if s.eit_schedule else "false",
            "EIT_present_following": "true" if s.eit_pf else "false",
            "CA_mode": "true" if s.free_ca_mode else "false",
            "running_status": _RUN_OUT[s.running_status],
        })
        ET.SubElement(sv, "service_descriptor", {
            "service_type": "0x%02X" % int(s.service_type),
            "service_provider_name": s.provider,
            "service_name": s.name,
        })
    return el


def write_bat(b: Bouquet) -> ET.Element:
    el = ET.Element("BAT", {
        "version": str(b.version),
        "current": "true",
        "bouquet_id": _hex16(b.bouquet_id),
    })
    ET.SubElement(el, "bouquet_name_descriptor", {"bouquet_name": b.name})
    _put_pds(el, b.private_data_specifier)
    if b.linkages_on:
        for lk in b.linkages:
            _put_linkage(el, lk)
    for loop in b.ts_loops:
        ts = ET.SubElement(el, "transport_stream", {
            "transport_stream_id": _hex16(loop.ts_id),
            "original_network_id": _hex16(loop.original_network_id),
            "preferred_section": str(loop.preferred_section),
        })
        _put_service_list(ts, loop.services)
        # PDS phải đứng TRƯỚC descriptor LCN, nếu không đầu thu không hiểu.
        _put_pds(ts, loop.private_data_specifier)
        if loop.lcn:
            lcn_el = ET.SubElement(ts, LCN_DESCRIPTOR)
            for e in loop.lcn:
                ET.SubElement(lcn_el, "service", {
                    "service_id": _hex16(e.service_id),
                    "logical_channel_number": str(e.lcn),
                    "visible_service": "true" if e.visible else "false",
                })
    return el


# ------------------------------------------------------------------ SO SÁNH


def _value(text: str):
    """Chuẩn hoá một giá trị thuộc tính về kiểu so sánh được."""
    t = text.strip()
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return num(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def canon(el: ET.Element, skip: frozenset[str] = frozenset({"metadata"})):
    """Dạng chuẩn hoá của một cây, so được theo *giá trị*.

    Bỏ ``<metadata>`` vì nó là chú thích của công cụ chứ không phải nội dung
    bảng. Giữ nguyên **thứ tự phần tử con** — thứ tự descriptor có ý nghĩa
    thật trên sóng, nên hai cây khác thứ tự là hai cây khác nhau.
    """
    attrs = tuple(sorted((k, _value(v)) for k, v in el.attrib.items()))
    text = " ".join((el.text or "").split()) or None
    kids = tuple(canon(c, skip) for c in el if c.tag not in skip)
    return (el.tag, attrs, text, kids)
