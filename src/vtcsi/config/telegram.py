"""Đọc và ghi ``config/telegram.yaml`` — vỏ có I/O.

**File này KHÔNG vào git.** Nó chứa token bot, mà kho của dự án là kho công
khai trên GitHub. Một token lọt lên đó thì ai cũng gửi tin được vào nhóm chat
vận hành, và xoá commit không lấy lại được gì — token phải thu hồi rồi cấp
lại. Nên nó nằm cùng nhóm với ``dau-ra.yaml``, khác ``toc-do.yaml``.

Hệ quả: mỗi máy phải cấu hình riêng. Đổi lại là ``ten_may`` — hai máy dự phòng
cùng bắn vào một nhóm chat, không có tên thì không biết tin nào của máy nào.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path

import yaml

from vtcsi.model.telegram import Cai, TelegramError, validate

FILE = "telegram.yaml"

_HEADER = """\
# Thông báo Telegram. Sinh bởi vtcsi, sửa tay cũng được.
#
# FILE NÀY KHÔNG VÀO GIT: nó chứa token bot, mà kho của dự án là kho công khai.
# Token lọt lên đó thì phải thu hồi rồi cấp lại, xoá commit không cứu được.
#
# Lấy token: nhắn @BotFather trên Telegram, /newbot.
# Lấy chat id: thêm bot vào nhóm, gửi một tin, rồi mở
#   https://api.telegram.org/bot<TOKEN>/getUpdates
"""


def path_for(root: Path) -> Path:
    return Path(root) / FILE


def load(root: Path) -> Cai:
    """Đọc cấu hình. Thiếu file thì trả mặc định — tức **tắt**."""
    p = path_for(root)
    if not p.exists():
        return Cai()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TelegramError(f"{FILE}: không đọc được YAML ({exc})") from exc
    if data is None:
        return Cai()
    if not isinstance(data, dict):
        raise TelegramError(f"{FILE}: nội dung phải là một khối khoá–giá trị")

    biet = {f.name for f in fields(Cai)}
    la = sorted(set(data) - biet)
    if la:
        raise TelegramError(f"{FILE}: không hiểu khoá {', '.join(la)}")

    ra = {}
    for f in fields(Cai):
        v = data.get(f.name, getattr(Cai(), f.name))
        if f.type == "bool" or isinstance(getattr(Cai(), f.name), bool):
            if not isinstance(v, bool):
                raise TelegramError(f"{FILE}: {f.name} phải là true hoặc false")
        elif isinstance(getattr(Cai(), f.name), int):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TelegramError(f"{FILE}: {f.name} phải là số nguyên")
        else:
            v = "" if v is None else str(v)
        ra[f.name] = v
    c = Cai(**ra)
    validate(c)
    return c


def save(c: Cai, root: Path) -> Path:
    """Ghi cấu hình. Kiểm trước khi ghi."""
    validate(c)
    p = path_for(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    than = yaml.safe_dump(asdict(c), allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    p.write_text(_HEADER + than, encoding="utf-8")
    try:
        p.chmod(0o600)          # token — khong de nguoi khac tren may doc duoc
    except OSError:
        pass                    # he tep khong ho tro thi thoi, khong phai loi
    return p
