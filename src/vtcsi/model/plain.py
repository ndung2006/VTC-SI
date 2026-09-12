"""Mô hình ↔ dict thuần — tầng giữa của cấu hình YAML.

Tách riêng khỏi YAML có chủ đích: việc ánh xạ cấu trúc là **thuần và test được
không cần thư viện nào**, còn ``config/loader.py`` chỉ còn mỗi việc đọc ghi file.

Dạng dict ở đây theo **cách người vận hành nghĩ**, không theo cách sóng xếp
byte. Khác biệt lớn nhất: một transport stream là *một* mục có cả tham số phát
lẫn danh sách dịch vụ, trong khi trên sóng chúng nằm ở hai bảng khác nhau.

Hệ quả quan trọng — **``service_list_descriptor`` không có trong cấu hình**.
Nó được suy từ danh sách dịch vụ mỗi lần sinh bảng (FR-3). Đã đối chiếu với
sóng thật: cùng tập, cùng thứ tự, cùng ``service_type`` ở cả ba TS. Thêm kênh
vào SDT mà quên NIT là lỗi kinh điển làm mất kênh; ở đây nó không xảy ra được.
"""

from __future__ import annotations

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
    RunningStatus,
    RollOff,
    SatelliteDelivery,
    SdtTable,
    Service,
    ServiceRef,
    ServiceType,
)


class ConfigError(ValueError):
    """Cấu hình sai cấu trúc. Luôn nói rõ chỗ sai."""


# ------------------------------------------------------------- tiện ích kiểu

def _hex(v: int, width: int = 4) -> str:
    return "0x%0*X" % (width, v)


def _int(v, what: str) -> int:
    """Nhận cả ``0x6510`` lẫn ``25872`` — người viết cấu hình dùng cả hai."""
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        t = v.strip().replace(",", "")
        try:
            return int(t, 16) if t.lower().startswith("0x") else int(t)
        except ValueError:
            pass
    raise ConfigError(f"{what}: không phải số nguyên: {v!r}")


def _bytes(v) -> bytes:
    if not v:
        return b""
    if isinstance(v, bytes):
        return v
    return bytes.fromhex(str(v).replace(" ", ""))


def _hexbytes(b: bytes) -> str:
    return " ".join("%02X" % x for x in b)


def _pds_out(v):
    return v if v is None or isinstance(v, str) else _hex(v, 8)


def _pds_in(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    t = str(v).strip()
    try:
        return _int(t, "private_data_specifier")
    except ConfigError:
        return t


def _need(d: dict, key: str, where: str):
    if key not in d:
        raise ConfigError(f"{where}: thiếu trường '{key}'")
    return d[key]


# ------------------------------------------------------------------- linkage

def _linkage_out(lk: Linkage) -> dict:
    out = {
        "linkage_type": _hex(lk.linkage_type, 2),
        "ts_id": lk.ts_id,
        "original_network_id": lk.original_network_id,
        "service_id": lk.service_id,
    }
    if lk.private_data:
        out["private_data"] = _hexbytes(lk.private_data)
    return out


def _linkage_in(d: dict, where: str) -> Linkage:
    return Linkage(
        linkage_type=_int(_need(d, "linkage_type", where), where + ".linkage_type"),
        ts_id=_int(d.get("ts_id", 0), where + ".ts_id"),
        original_network_id=_int(d.get("original_network_id", 0), where + ".onid"),
        service_id=_int(d.get("service_id", 0), where + ".service_id"),
        private_data=_bytes(d.get("private_data")),
    )


# ------------------------------------------------------------------ delivery

_POL = {p.name.lower().replace("linear_", "").replace("circular_", "circular-"): p
        for p in Polarization}
_POL_OUT = {v: k for k, v in _POL.items()}
_ROLL = {"0.35": RollOff.A_035, "0.25": RollOff.A_025, "0.20": RollOff.A_020}
_ROLL_OUT = {v: k for k, v in _ROLL.items()}
_SYS = {"DVB-S": ModulationSystem.DVB_S, "DVB-S2": ModulationSystem.DVB_S2}
_SYS_OUT = {v: k for k, v in _SYS.items()}
_MOD = {"auto": ModulationType.AUTO, "QPSK": ModulationType.QPSK,
        "8PSK": ModulationType.PSK_8, "16-QAM": ModulationType.QAM_16}
_MOD_OUT = {v: k for k, v in _MOD.items()}
_FEC = {"1/2": FecInner.F_1_2, "2/3": FecInner.F_2_3, "3/4": FecInner.F_3_4,
        "5/6": FecInner.F_5_6, "7/8": FecInner.F_7_8, "8/9": FecInner.F_8_9,
        "3/5": FecInner.F_3_5, "4/5": FecInner.F_4_5, "9/10": FecInner.F_9_10}
_FEC_OUT = {v: k for k, v in _FEC.items()}
_RUN = {r.name.lower(): r for r in RunningStatus}
_RUN_OUT = {v: k for k, v in _RUN.items()}


def _delivery_out(d: SatelliteDelivery) -> dict:
    return {
        "system": _SYS_OUT[d.modulation_system],
        "modulation": _MOD_OUT[d.modulation_type],
        "frequency_hz": d.frequency_hz,
        "polarization": _POL_OUT[d.polarization],
        "symbol_rate_sps": d.symbol_rate_sps,
        "fec_inner": _FEC_OUT[d.fec_inner],
        "roll_off": _ROLL_OUT[d.roll_off],
        "orbital_position": d.orbital_position_deg,
        "east": d.east,
    }


def _delivery_in(d: dict, where: str) -> SatelliteDelivery:
    def pick(table, key, default=None):
        raw = d.get(key, default)
        if raw not in table:
            raise ConfigError(f"{where}.{key}: giá trị lạ {raw!r}")
        return table[raw]

    return SatelliteDelivery(
        frequency_hz=_int(_need(d, "frequency_hz", where), where + ".frequency_hz"),
        orbital_position_deg=float(_need(d, "orbital_position", where)),
        east=bool(d.get("east", True)),
        polarization=pick(_POL, "polarization"),
        symbol_rate_sps=_int(_need(d, "symbol_rate_sps", where), where + ".symbol_rate_sps"),
        fec_inner=pick(_FEC, "fec_inner"),
        modulation_system=pick(_SYS, "system", "DVB-S2"),
        modulation_type=pick(_MOD, "modulation", "8PSK"),
        roll_off=pick(_ROLL, "roll_off", "0.25"),
    )


# ---------------------------------------------------------------------- ghi

def to_plain(cfg: Config) -> dict:
    """Mô hình thành dict thuần, gộp vòng NIT với bảng SDT theo từng TS."""
    sdt_by_ts = {s.ts_id: s for s in cfg.sdts}
    streams = []
    for loop in cfg.network.ts_loops:
        sdt = sdt_by_ts.get(loop.ts_id)
        if sdt is None:
            raise ConfigError(f"TS {loop.ts_id} có trong NIT nhưng không có SDT")
        streams.append({
            "ts_id": loop.ts_id,
            "original_network_id": loop.original_network_id,
            "actual": sdt.actual,
            "sdt_version": sdt.version,
            "delivery": _delivery_out(loop.delivery) if loop.delivery else None,
            "private_data_specifier": _pds_out(loop.private_data_specifier),
            "services": [
                {
                    "service_id": s.service_id,
                    "name": s.name,
                    "provider": s.provider,
                    "type": int(s.service_type),
                    "running_status": _RUN_OUT[s.running_status],
                    "free_ca_mode": s.free_ca_mode,
                    "eit_pf": s.eit_pf,
                    "eit_schedule": s.eit_schedule,
                }
                for s in sdt.services
            ],
        })

    bouquets = []
    for b in cfg.bouquets:
        bouquets.append({
            "bouquet_id": _hex(b.bouquet_id),
            "name": b.name,
            "version": b.version,
            "private_data_specifier": _pds_out(b.private_data_specifier),
            "linkages": [_linkage_out(x) for x in b.linkages],
            "transport_streams": [
                {
                    "ts_id": t.ts_id,
                    "original_network_id": t.original_network_id,
                    "private_data_specifier": _pds_out(t.private_data_specifier),
                    "services": [r.service_id for r in t.services],
                    "lcn": [
                        {"service_id": e.service_id, "lcn": e.lcn, "visible": e.visible}
                        for e in t.lcn
                    ],
                }
                for t in b.ts_loops
            ],
        })

    return {
        "network": {
            "network_id": cfg.network.network_id,
            "name": cfg.network.name,
            "version": cfg.network.version,
            "actual": cfg.network.actual,
            "linkages": [_linkage_out(x) for x in cfg.network.linkages],
            "transport_streams": streams,
        },
        "bouquets": bouquets,
    }


# ---------------------------------------------------------------------- đọc

def from_plain(data: dict) -> Config:
    """Dict thuần thành mô hình, suy ``service_list`` từ danh sách dịch vụ."""
    net = _need(data, "network", "goc")
    loops, sdts = [], []
    types: dict[tuple[int, int], int] = {}

    for raw in _need(net, "transport_streams", "network"):
        ts_id = _int(_need(raw, "ts_id", "transport_stream"), "ts_id")
        where = f"TS {ts_id}"
        onid = _int(_need(raw, "original_network_id", where), where + ".onid")

        services = []
        for s in raw.get("services", []):
            sid = _int(_need(s, "service_id", where), where + ".service_id")
            stype = _int(s.get("type", 1), where + ".type")
            types[(ts_id, sid)] = stype
            services.append(Service(
                service_id=sid,
                name=s.get("name", ""),
                provider=s.get("provider", ""),
                service_type=ServiceType(stype),
                running_status=_RUN[s.get("running_status", "running")],
                free_ca_mode=bool(s.get("free_ca_mode", False)),
                eit_pf=bool(s.get("eit_pf", True)),
                eit_schedule=bool(s.get("eit_schedule", True)),
            ))

        deliv = raw.get("delivery")
        loops.append(NitTsLoop(
            ts_id=ts_id,
            original_network_id=onid,
            delivery=_delivery_in(deliv, where + ".delivery") if deliv else None,
            # FR-3: suy ra, khong cho go tay
            services=tuple(ServiceRef(s.service_id, int(s.service_type)) for s in services),
            private_data_specifier=_pds_in(raw.get("private_data_specifier")),
        ))
        sdts.append(SdtTable(
            ts_id=ts_id,
            original_network_id=onid,
            version=_int(_need(raw, "sdt_version", where), where + ".sdt_version"),
            actual=bool(raw.get("actual", False)),
            services=tuple(services),
        ))

    bouquets = []
    for raw in data.get("bouquets", []):
        bid = _int(_need(raw, "bouquet_id", "bouquet"), "bouquet_id")
        where = f"bouquet {_hex(bid)}"
        ts_loops = []
        for t in raw.get("transport_streams", []):
            ts_id = _int(_need(t, "ts_id", where), where + ".ts_id")
            refs = []
            for sid_raw in t.get("services", []):
                sid = _int(sid_raw, where + ".services")
                if (ts_id, sid) not in types:
                    raise ConfigError(
                        f"{where}: dịch vụ {sid} không có trong TS {ts_id}")
                refs.append(ServiceRef(sid, types[(ts_id, sid)]))
            ts_loops.append(BatTsLoop(
                ts_id=ts_id,
                original_network_id=_int(_need(t, "original_network_id", where), where),
                services=tuple(refs),
                private_data_specifier=_pds_in(t.get("private_data_specifier")),
                lcn=tuple(
                    LcnEntry(
                        service_id=_int(e["service_id"], where + ".lcn"),
                        lcn=_int(e["lcn"], where + ".lcn"),
                        visible=bool(e.get("visible", True)),
                    )
                    for e in t.get("lcn", [])
                ),
            ))
        bouquets.append(Bouquet(
            bouquet_id=bid,
            name=raw.get("name", ""),
            version=_int(_need(raw, "version", where), where + ".version"),
            private_data_specifier=_pds_in(raw.get("private_data_specifier")),
            linkages=tuple(_linkage_in(x, where) for x in raw.get("linkages", [])),
            ts_loops=tuple(ts_loops),
        ))

    # Thu tu vong transport trong NIT CO y nghia tren song nen giu nguyen theo
    # cau hinh. Thu tu cac bang SDT thi KHONG — chung la sub-table roi nhau — nen
    # sap theo ts_id cho tat dinh, giong het read_dump.
    sdts.sort(key=lambda s: s.ts_id)

    return Config(
        network=Network(
            network_id=_int(_need(net, "network_id", "network"), "network_id"),
            name=net.get("name", ""),
            version=_int(_need(net, "version", "network"), "network.version"),
            actual=bool(net.get("actual", True)),
            linkages=tuple(_linkage_in(x, "network") for x in net.get("linkages", [])),
            ts_loops=tuple(loops),
        ),
        sdts=tuple(sdts),
        bouquets=tuple(bouquets),
    )
