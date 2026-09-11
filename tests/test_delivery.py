"""AC-1 — vector byte cố định cho ``satellite_delivery_system_descriptor``.

Ba vector lấy từ cấu hình Barrowa đang chạy, xem ``spec.md`` Phụ lục A.3.
Đây là phép thử đầu tiên của dự án: nếu ba dòng này xanh thì cách tiếp cận
byte-đối-byte đứng vững.

Chạy được bằng cả hai cách, không cần cài gì:
    python -m unittest discover -s tests -t .
    pytest
"""

from __future__ import annotations

import unittest

from vtcsi.model.entities import (
    FecInner,
    ModulationSystem,
    ModulationType,
    Polarization,
    RollOff,
    SatelliteDelivery,
)
from vtcsi.tables import delivery

# Ba transport stream của VTC. Cả ba: 132,0°E, DVB-S2, 8PSK, roll-off 0,25.
TS8 = SatelliteDelivery(
    frequency_hz=10_968_000_000,
    orbital_position_deg=132.0,
    east=True,
    polarization=Polarization.LINEAR_HORIZONTAL,
    symbol_rate_sps=28_800_000,
    fec_inner=FecInner.F_3_4,
)
TS3 = SatelliteDelivery(
    frequency_hz=11_088_000_000,
    orbital_position_deg=132.0,
    east=True,
    polarization=Polarization.LINEAR_VERTICAL,
    symbol_rate_sps=18_750_000,
    fec_inner=FecInner.F_5_6,
)
TS1000 = SatelliteDelivery(
    frequency_hz=11_589_000_000,
    orbital_position_deg=132.0,
    east=True,
    polarization=Polarization.LINEAR_HORIZONTAL,
    symbol_rate_sps=15_000_000,
    fec_inner=FecInner.F_3_4,
)

VECTORS = {
    "TSID 8": (TS8, "43 0B 01 09 68 00 13 20 8E 02 88 00 03"),
    "TSID 3": (TS3, "43 0B 01 10 88 00 13 20 AE 01 87 50 04"),
    "TSID 1000": (TS1000, "43 0B 01 15 89 00 13 20 8E 01 50 00 03"),
}


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


class TestSatelliteDeliveryVectors(unittest.TestCase):
    def test_vectors(self) -> None:
        for name, (params, expected) in VECTORS.items():
            with self.subTest(ts=name):
                self.assertEqual(_hex(delivery.encode(params)), expected)

    def test_length_is_always_13(self) -> None:
        """Tag + length + 11 byte payload, không đổi."""
        for name, (params, _) in VECTORS.items():
            with self.subTest(ts=name):
                out = delivery.encode(params)
                self.assertEqual(len(out), 13)
                self.assertEqual(out[0], delivery.TAG)
                self.assertEqual(out[1], delivery.PAYLOAD_LEN)


class TestFlagsByte(unittest.TestCase):
    """Byte nhồi năm trường vào tám bit — tách ra thử riêng."""

    def test_ts8_flags(self) -> None:
        # đông=1 · ngang=00 · roll-off 0,25=01 · S2=1 · 8PSK=10 -> 0b1000_1110
        self.assertEqual(delivery._flags_byte(TS8), 0x8E)

    def test_vertical_polarization_flips_one_field_only(self) -> None:
        self.assertEqual(delivery._flags_byte(TS3), 0xAE)
        self.assertEqual(delivery._flags_byte(TS8) ^ delivery._flags_byte(TS3), 0b0010_0000)

    def test_roll_off_ignored_on_dvb_s(self) -> None:
        """Với DVB-S, trường roll_off là dự trữ và phải ra 0."""
        s1 = SatelliteDelivery(
            frequency_hz=10_968_000_000,
            orbital_position_deg=132.0,
            east=True,
            polarization=Polarization.LINEAR_HORIZONTAL,
            symbol_rate_sps=28_800_000,
            fec_inner=FecInner.F_3_4,
            modulation_system=ModulationSystem.DVB_S,
            modulation_type=ModulationType.QPSK,
            roll_off=RollOff.A_035,
        )
        # đông=1 · ngang=00 · dự trữ=00 · S=0 · QPSK=01
        self.assertEqual(delivery._flags_byte(s1), 0b1000_0001)


class TestRefusesLossyInput(unittest.TestCase):
    """BCD không biểu diễn được thì phải báo lỗi, không được làm tròn im lặng."""

    def test_frequency_not_on_10khz_grid(self) -> None:
        bad = SatelliteDelivery(
            frequency_hz=10_968_000_001,
            orbital_position_deg=132.0,
            east=True,
            polarization=Polarization.LINEAR_HORIZONTAL,
            symbol_rate_sps=28_800_000,
            fec_inner=FecInner.F_3_4,
        )
        with self.assertRaises(ValueError):
            delivery.encode(bad)

    def test_symbol_rate_not_on_100sps_grid(self) -> None:
        bad = SatelliteDelivery(
            frequency_hz=10_968_000_000,
            orbital_position_deg=132.0,
            east=True,
            polarization=Polarization.LINEAR_HORIZONTAL,
            symbol_rate_sps=28_800_001,
            fec_inner=FecInner.F_3_4,
        )
        with self.assertRaises(ValueError):
            delivery.encode(bad)


class TestDeterminism(unittest.TestCase):
    """AC-12 ở quy mô nhỏ: cùng đầu vào, cùng byte, mọi lần."""

    def test_repeated_encode_is_identical(self) -> None:
        first = delivery.encode(TS8)
        for _ in range(100):
            self.assertEqual(delivery.encode(TS8), first)


if __name__ == "__main__":
    unittest.main()
