"""Kiểm tra trước khi đấu nối — FR-18.

**Đây là một lệnh, không phải cổng chặn lúc chạy.** Tiến trình phát không bao
giờ tự dừng vì không đọc được luồng tham chiếu: mất tham chiếu không phải bằng
chứng mình sai, và nếu nguồn kia vừa chết thì đó chính là lúc mình cần phát
nhất (§3.5 của ``spec.md``). Nên phép kiểm tra này chạy khi người ta gọi, rồi
người ta quyết định.

Việc của module: ghép ba thứ — cấu hình, bảng trên sóng, và quy tắc version —
thành một báo cáo đọc được.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from vtcsi.model.entities import Config
from vtcsi.model.version import BLOCKING, Verdict, classify, explain
from vtcsi.tables import tsduck as T


@dataclass(frozen=True, slots=True)
class Row:
    """Kết quả cho một bảng."""

    name: str
    config_version: int | None
    air_version: int | None
    content_same: bool
    verdict: Verdict | None

    @property
    def blocking(self) -> bool:
        return self.verdict in BLOCKING if self.verdict else True

    def line(self) -> str:
        if self.verdict is None:
            side = "chi co trong cau hinh" if self.air_version is None \
                else "chi co tren song"
            return f"  {self.name:<14} THIEU — {side}"
        mark = "!!" if self.blocking else "  "
        note = explain(self.verdict, config_version=self.config_version,
                       air_version=self.air_version)
        return f"{mark} {self.name:<14} {self.verdict.value:<16} {note}"


@dataclass(frozen=True, slots=True)
class Report:
    rows: tuple[Row, ...]

    @property
    def blocking(self) -> tuple[Row, ...]:
        return tuple(r for r in self.rows if r.blocking)

    @property
    def ok(self) -> bool:
        return not self.blocking

    def text(self) -> str:
        out = [r.line() for r in self.rows]
        if self.ok:
            out.append(f"\n{len(self.rows)}/{len(self.rows)} bang khong co van de.")
        else:
            out.append(f"\n{len(self.blocking)}/{len(self.rows)} bang can xu ly "
                       f"truoc khi phat.")
        return "\n".join(out)


def _tables(cfg: Config) -> dict[str, ET.Element]:
    """Mọi bảng cấu trúc, đặt tên theo cách người vận hành gọi."""
    out = {"NIT": T.write_nit(cfg.network)}
    for s in cfg.sdts:
        out[f"SDT ts{s.ts_id}"] = T.write_sdt(s)
    for b in cfg.bouquets:
        out[f"BAT {b.bouquet_id:04x}"] = T.write_bat(b)
    return out


def _versions(cfg: Config) -> dict[str, int]:
    out = {"NIT": cfg.network.version}
    out.update({f"SDT ts{s.ts_id}": s.version for s in cfg.sdts})
    out.update({f"BAT {b.bouquet_id:04x}": b.version for b in cfg.bouquets})
    return out


def _strip_version(el: ET.Element) -> ET.Element:
    clone = ET.fromstring(ET.tostring(el, encoding="unicode"))
    clone.attrib.pop("version", None)
    return clone


def check(cfg: Config, air: Config) -> Report:
    """So cấu hình với bảng đang trên sóng, từng bảng một."""
    mine, theirs = _tables(cfg), _tables(air)
    my_v, their_v = _versions(cfg), _versions(air)

    rows = []
    for name in sorted(set(mine) | set(theirs)):
        if name not in mine or name not in theirs:
            rows.append(Row(name, my_v.get(name), their_v.get(name), False, None))
            continue
        # So noi dung KHONG ke version — version la cai dang duoc xet rieng.
        same = T.canon(_strip_version(mine[name])) == T.canon(_strip_version(theirs[name]))
        rows.append(Row(
            name=name,
            config_version=my_v[name],
            air_version=their_v[name],
            content_same=same,
            verdict=classify(config_version=my_v[name],
                             air_version=their_v[name],
                             content_same=same),
        ))
    return Report(tuple(rows))


def check_against_dump(cfg: Config, dump_xml: str) -> Report:
    return check(cfg, T.read_dump(dump_xml))
