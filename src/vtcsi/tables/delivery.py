"""``satellite_delivery_system_descriptor`` — tag ``0x43``.

Descriptor delivery duy nhất trong phạm vi hệ này, vì phạm vi là thuần vệ tinh.
Payload cố định 11 byte. EN 300 468 §6.2.13.2.

Bố cục::

    descriptor_tag        8   0x43
    descriptor_length     8   11
    frequency            32   BCD 8 chữ số, GHz, dấu thập phân sau chữ số thứ 3
    orbital_position     16   BCD 4 chữ số, đơn vị 0,1 độ
    west_east_flag        1
    polarization          2
    roll_off              2   chỉ có nghĩa khi modulation_system = DVB-S2
    modulation_system     1
    modulation_type       2
    symbol_rate          28   BCD 7 chữ số, MS/s, dấu thập phân sau chữ số thứ 3
    FEC_inner             4

Hàm thuần: vào là mô hình, ra là byte. Không I/O, không đồng hồ.
"""

from __future__ import annotations

from vtcsi.model.entities import ModulationSystem, SatelliteDelivery

TAG = 0x43
PAYLOAD_LEN = 11


def _bcd(value: int, digits: int) -> bytes:
    """Mã hoá ``value`` thành ``digits`` chữ số BCD gói đôi.

    ``digits`` phải chẵn — mọi trường BCD trong descriptor này đều chẵn trừ
    symbol_rate, vốn được ghép với FEC_inner cho tròn byte.
    """
    if value < 0:
        raise ValueError("BCD không mã hoá được số âm")
    if digits % 2:
        raise ValueError("số chữ số phải chẵn; trường lẻ phải tự ghép nibble")
    s = f"{value:0{digits}d}"
    if len(s) != digits:
        raise ValueError(f"{value} vượt quá {digits} chữ số BCD")
    return bytes(int(s[i : i + 2], 16) for i in range(0, digits, 2))


def _freq_digits(frequency_hz: int) -> int:
    """Hz sang 8 chữ số BCD theo GHz, dấu thập phân sau chữ số thứ ba.

    Chữ số cuối có trọng số 10^-5 GHz, tức 10 kHz.
    """
    if frequency_hz % 10_000:
        raise ValueError(f"tần số {frequency_hz} Hz không tròn 10 kHz, BCD sẽ mất chính xác")
    return frequency_hz // 10_000


def _symbol_rate_digits(symbol_rate_sps: int) -> int:
    """Symbol/s sang 7 chữ số BCD theo MS/s, dấu thập phân sau chữ số thứ ba.

    Chữ số cuối có trọng số 10^-4 MS/s, tức 100 symbol/s.
    """
    if symbol_rate_sps % 100:
        raise ValueError(f"symbol rate {symbol_rate_sps} không tròn 100 S/s, BCD sẽ mất chính xác")
    return symbol_rate_sps // 100


def _flags_byte(d: SatelliteDelivery) -> int:
    """Byte nhồi năm trường vào tám bit — chỗ dễ sai nhất của descriptor này."""
    roll_off = d.roll_off if d.modulation_system is ModulationSystem.DVB_S2 else 0
    return (
        (0b1 if d.east else 0b0) << 7
        | (int(d.polarization) & 0b11) << 5
        | (int(roll_off) & 0b11) << 3
        | (int(d.modulation_system) & 0b1) << 2
        | (int(d.modulation_type) & 0b11)
    )


def encode(d: SatelliteDelivery) -> bytes:
    """Dựng descriptor đầy đủ, gồm cả tag và length."""
    freq = _bcd(_freq_digits(d.frequency_hz), 8)

    orbital = round(d.orbital_position_deg * 10)
    if not 0 <= orbital <= 9999:
        raise ValueError(f"vị trí quỹ đạo {d.orbital_position_deg} ngoài dải BCD 4 chữ số")
    orb = _bcd(orbital, 4)

    # symbol_rate 28 bit + FEC_inner 4 bit = đúng 4 byte, nên ghép nibble tay.
    sr = f"{_symbol_rate_digits(d.symbol_rate_sps):07d}"
    if len(sr) != 7:
        raise ValueError(f"symbol rate {d.symbol_rate_sps} vượt quá 7 chữ số BCD")
    nibbles = [int(c) for c in sr] + [int(d.fec_inner) & 0x0F]
    sr_fec = bytes(nibbles[i] << 4 | nibbles[i + 1] for i in range(0, 8, 2))

    payload = freq + orb + bytes([_flags_byte(d)]) + sr_fec
    assert len(payload) == PAYLOAD_LEN, "payload phải đúng 11 byte"
    return bytes([TAG, PAYLOAD_LEN]) + payload
