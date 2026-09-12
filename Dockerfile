# vtcsi — bộ sinh bảng báo hiệu PSI/SI cho VTC DVB-S
#
# Một ảnh, hai vai: `vtcsi run` phát sóng, `vtcsi web` nhập liệu. Cùng một ảnh
# vì cả hai đọc **cùng một thư mục cấu hình trong git** — tách ảnh ra là tạo
# cơ hội cho hai bên lệch phiên bản, đúng thứ hệ này sinh ra để tránh.
#
# TSDuck cài từ gói .deb chính thức chứ không build từ nguồn: build mất hơn
# mười phút và kéo theo cả bộ biên dịch vào ảnh cuối.

FROM debian:trixie-slim AS tsduck

ARG TSDUCK_VERSION=3.44-4676
ARG TARGETARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Phiên bản ghim tường minh. Tự nâng TSDuck nghĩa là tự đổi byte trên sóng mà
# không ai duyệt — và với hai nguồn ngang hàng thì chỉ cần một bên nâng là
# phép so byte giữa hai bên hết đúng.
#
# Nền là **trixie**, không phải bookworm: TSDuck 3.44 chỉ phát hành gói
# `debian13`. Nâng phiên bản thì kiểm lại tên gói trước — chúng có đổi.
# Xem https://github.com/tsduck/tsduck/releases
RUN curl -fsSL -o /tmp/tsduck.deb \
      "https://github.com/tsduck/tsduck/releases/download/v${TSDUCK_VERSION}/tsduck_${TSDUCK_VERSION}.debian13_${TARGETARCH}.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/tsduck.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/tsduck.deb


FROM tsduck AS app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git tini \
    && rm -rf /var/lib/apt/lists/*

# git là phụ thuộc thật, không phải tiện ích: giao diện nhập liệu commit mỗi
# thay đổi, và git là cơ chế đồng bộ giữa hai hệ (§3.3 spec.md).

ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN python3 -m venv "$VIRTUAL_ENV"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[web]"

# Cấu hình **không** nằm trong ảnh. Nó là một kho git gắn vào lúc chạy, vì
# nguồn sự thật là lịch sử git chứ không phải ảnh container — sửa một tên kênh
# không được đòi dựng lại ảnh rồi triển khai lại.
#
# Gắn vào là **cả kho**, không phải riêng `config/`: giao diện chạy `git diff`
# và `git commit`, mà hai lệnh đó cần thư mục `.git` nằm đúng chỗ của nó. Gắn
# riêng `config/` thì vẫn sửa được nhưng mất lịch sử — tức mất cơ chế đồng bộ.
VOLUME ["/repo", "/build"]

# Kho gan tu ngoai vao thuong lech chu so huu voi nguoi dung trong container.
RUN git config --system --add safe.directory '*'

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD vtcsi --config /repo/config validate || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]

# Mặc định là chế độ in ra rồi thoát, KHÔNG phải phát sóng.
#
# Chạy một ảnh mới mà nó lập tức bơm multicast vào mạng nhà đài là cách hỏng
# tệ nhất có thể. Muốn phát thì phải nói ra — xem docker-compose.yml.
CMD ["vtcsi", "--config", "/repo/config", "validate"]
