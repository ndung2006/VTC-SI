"""Gọi Telegram Bot API — vỏ có I/O.

**Luật số một của file này: không bao giờ làm gián đoạn việc phát sóng.**
Telegram là mạng ngoài; nó có thể chậm, treo, đổi chứng chỉ, hoặc bị chặn ở
tường lửa cơ quan. Nên mọi lối vào đều:

* có **hạn giờ** cứng, không bao giờ chờ vô hạn;
* **nuốt mọi lỗi** và ghi log, không ném ngược vào đường sinh bảng;
* chạy **nền** ở đường nóng, để người bấm Lưu không phải chờ một máy chủ ở
  nước ngoài trả lời.

Dùng ``urllib`` của thư viện chuẩn chứ không thêm phụ thuộc: một gói HTTP nữa
trong ảnh Docker của hệ phát sóng là một thứ nữa phải vá khi có CVE, đổi lấy
việc tiết kiệm mười lăm dòng.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Callable

from vtcsi.model.telegram import Cai

API = "https://api.telegram.org/bot{token}/sendMessage"

HAN_GIO = 8.0
"""Giây. Đủ rộng cho một đường ra chậm, đủ hẹp để không giữ luồng nền lâu."""


def gui(c: Cai, text: str, *, han_gio: float = HAN_GIO,
        mo: Callable | None = None) -> tuple[bool, str]:
    """Gửi một tin. Trả ``(thành công, lời giải thích)``. **Không bao giờ ném.**

    ``mo`` là chỗ tiêm cho bài kiểm — mặc định là ``urlopen`` thật. Bài kiểm
    không được chạm mạng: một bộ kiểm cần Internet là một bộ kiểm sẽ đỏ vào
    đúng hôm mạng cơ quan trục trặc, và rồi không ai tin nó nữa.
    """
    if not c.san_sang:
        return False, "chưa bật hoặc thiếu token/chat id"
    du_lieu = json.dumps({
        "chat_id": c.chat_id.strip(),
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    yeu_cau = urllib.request.Request(
        API.format(token=c.token.strip()), data=du_lieu,
        headers={"Content-Type": "application/json"}, method="POST")
    opener = mo or urllib.request.urlopen
    try:
        with opener(yeu_cau, timeout=han_gio) as tra:
            than = tra.read().decode("utf-8", "replace")
        ket = json.loads(than)
        if ket.get("ok"):
            return True, "đã gửi"
        # Bot API tra loi 200 kem ok=false — doc description, no noi ro chuyen gi.
        return False, str(ket.get("description") or than)[:200]
    except urllib.error.HTTPError as exc:
        chi_tiet = ""
        try:
            chi_tiet = json.loads(exc.read().decode("utf-8", "replace")) \
                .get("description", "")
        except Exception:       # noqa: BLE001 — doc them la co gang, khong bat buoc
            pass
        return False, f"HTTP {exc.code} {chi_tiet}".strip()
    except Exception as exc:    # noqa: BLE001 — XEM docstring module
        return False, f"{type(exc).__name__}: {exc}"


def gui_nen(c: Cai, text: str, *, ghi: Callable[[str], None] | None = None,
            mo: Callable | None = None) -> threading.Thread | None:
    """Gửi ở luồng nền. Trả luồng để bài kiểm chờ; nơi gọi thật bỏ qua.

    Đây là lối vào cho **đường nóng** — lúc lưu cấu hình, lúc nhận file lịch,
    lúc ``tsp`` chết. Không chỗ nào trong số đó được phép đứng chờ Telegram.
    """
    if not c.san_sang:
        return None

    def chay() -> None:
        xong, vi_sao = gui(c, text, mo=mo)
        if not xong and ghi:
            ghi(f"telegram: khong gui duoc — {vi_sao}")

    t = threading.Thread(target=chay, name="telegram", daemon=True)
    t.start()
    return t
