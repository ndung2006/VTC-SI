"""Thông báo Telegram — lõi thuần: gửi gì, có gửi không, soạn ra sao.

Không một dòng nào ở đây chạm mạng. Việc gọi Bot API là của
``vtcsi/notify/telegram.py``; tách ra vì phần **quyết định** mới là phần dễ
sai, và nó phải kiểm được mà không cần Telegram, không cần Internet, không cần
chờ.

Ba ràng buộc định hình toàn bộ thiết kế, cả ba đều học từ chỗ khác trong hệ:

**Không bao giờ chặn đường phát sóng.** Telegram là mạng ngoài — chậm, treo,
hoặc bị chặn đều có thể xảy ra. Nên nơi gọi phải chạy nền và nuốt lỗi; ở đây
chỉ cần biết rằng **không hàm nào trong file này được phép ném lỗi lúc soạn
tin**. Một cảnh báo hỏng mà làm sập việc sinh bảng thì tệ hơn là không có
cảnh báo.

**Token là bí mật, kho GitHub thì công khai.** Nên ``config/telegram.yaml``
nằm **ngoài git**, khác ``toc-do.yaml``. Mọi chỗ hiển thị token phải qua
``che``.

**Phải chống dội.** ``si`` chập chờn mà mỗi lần lên xuống một tin nhắn thì
nửa đêm sẽ có hàng trăm tin, và người trực sẽ tắt thông báo — lúc đó hệ mất
sạch tác dụng. Một cảnh báo bị tắt còn tệ hơn một cảnh báo không có, vì nó
tạo cảm giác đang được canh.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

#: Các loại việc báo, và tên hiển thị cho người vận hành.
LOAI = {
    "epg": "Có file lịch EPG mới",
    "nit": "Bảng NIT thay đổi",
    "thay-doi": "Thay đổi lớn ở cấu hình",
    "song": "Dịch vụ phát chạy / dừng",
}

#: Cửa sổ chống dội mặc định, tính bằng phút.
IM_LANG_PHUT = 5

MAX_KY_TU = 3_500
"""Telegram chặn ở 4096 ký tự. Cắt sớm hơn để còn chỗ cho phần đuôi."""


class TelegramError(ValueError):
    """Cấu hình không dùng được. Thông điệp đi thẳng ra giao diện."""


@dataclass(frozen=True, slots=True)
class Cai:
    """Cấu hình thông báo. Token và chat id lấy từ BotFather."""

    token: str = ""
    chat_id: str = ""
    bat: bool = False
    """Công tắc tổng. Mặc định **tắt**: một hệ vừa cài không được tự bắn tin
    ra ngoài khi chưa ai bảo nó làm vậy."""
    bao_epg: bool = True
    bao_nit: bool = True
    bao_thay_doi: bool = True
    bao_song: bool = True
    im_lang_phut: int = IM_LANG_PHUT
    ten_may: str = ""
    """Tên máy, ghép vào đầu mỗi tin. Hai máy dự phòng cùng bắn vào một nhóm
    chat thì không có cái này là không biết tin nào của máy nào."""

    @property
    def san_sang(self) -> bool:
        return bool(self.bat and self.token.strip() and self.chat_id.strip())


def validate(c: Cai) -> None:
    """Ném ``TelegramError`` ở chỗ đầu tiên không dùng được."""
    if c.bat and not c.token.strip():
        raise TelegramError("bật thông báo thì phải có token bot")
    if c.bat and not c.chat_id.strip():
        raise TelegramError("bật thông báo thì phải có chat id")
    if c.token and ":" not in c.token:
        raise TelegramError(
            "token bot sai dạng — BotFather cấp chuỗi kiểu "
            "'123456789:AAH...', có dấu hai chấm ở giữa")
    if not isinstance(c.im_lang_phut, int) or not 0 <= c.im_lang_phut <= 1440:
        raise TelegramError(f"cửa sổ chống dội phải từ 0 đến 1440 phút, "
                            f"đang là {c.im_lang_phut!r}")
    for f in fields(Cai):
        if f.name.startswith("bao_") and not isinstance(getattr(c, f.name), bool):
            raise TelegramError(f"{f.name} phải là true hoặc false")


def bat_loai(c: Cai, loai: str) -> bool:
    """Loại việc này có được báo không."""
    if not c.san_sang:
        return False
    return bool(getattr(c, "bao_" + loai.replace("-", "_"), False))


def che(token: str) -> str:
    """Token để hiển thị: giữ phần id, giấu phần bí mật.

    ``123456789:AAH...xyz`` thành ``123456789:••••••xyz``. Giữ id vì nó giúp
    người vận hành biết **bot nào**, mà nó không phải bí mật; giữ ba ký tự
    cuối để đối chiếu nhanh mà không lộ gì dùng được.
    """
    t = token.strip()
    if not t:
        return ""
    if ":" not in t:
        return "••••••" + t[-3:] if len(t) > 3 else "••••••"
    dau, _, duoi = t.partition(":")
    return f"{dau}:••••••{duoi[-3:]}" if len(duoi) > 3 else f"{dau}:••••••"


def soan(loai: str, tieu_de: str, dong: tuple[str, ...] = (),
         ten_may: str = "") -> str:
    """Một tin nhắn, dạng văn bản thuần.

    **Không dùng Markdown hay HTML của Telegram.** Tên kênh thật có ký tự
    ``_``, ``*``, ``[`` — đủ để Bot API từ chối cả tin nhắn với lỗi phân tích
    cú pháp, và lúc đó cảnh báo im lặng biến mất đúng hôm cần nó nhất. Văn bản
    thuần thì không bao giờ hỏng.
    """
    dau = LOAI.get(loai, loai)
    dong_dau = f"[{ten_may}] {dau}" if ten_may.strip() else dau
    than = [dong_dau, tieu_de] if tieu_de else [dong_dau]
    than += [x for x in dong if x]
    ra = "\n".join(than)
    if len(ra) <= MAX_KY_TU:
        return ra
    return ra[:MAX_KY_TU - 20].rstrip() + "\n… (cắt bớt)"


def nen_gui(khoa: str, bay_gio: float, da_gui: dict[str, float],
            im_lang_phut: int) -> bool:
    """Chống dội: cùng một ``khoa`` thì im trong ``im_lang_phut`` phút.

    Hàm thuần, **không tự cập nhật** ``da_gui`` — nơi gọi cập nhật sau khi gửi
    thành công. Gửi hỏng mà đã ghi nhận là đã gửi thì tin đó mất luôn, và
    không ai biết.

    ``im_lang_phut = 0`` tắt chống dội hẳn. Có để gỡ rối, không nên để vậy khi
    chạy thật.
    """
    if im_lang_phut <= 0:
        return True
    truoc = da_gui.get(khoa)
    return truoc is None or bay_gio - truoc >= im_lang_phut * 60
