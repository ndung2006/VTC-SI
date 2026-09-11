# Bản đồ hệ thống PSI/SI dự phòng — VTC

> Đồng bộ với `spec.md` phiên bản **0.9**. Bản đồ mã nguồn ở [`mindmap-software.md`](mindmap-software.md).
> Mermaid render được trên GitHub và trong VS Code với extension *Markdown Preview Mermaid Support*.

---

## 1. Bản đồ toàn hệ

```mermaid
mindmap
  root((Hệ PSI-SI dự phòng VTC))
    Mục tiêu
      Thoát phụ thuộc bản quyền Barrowa
      Có nguồn báo hiệu thứ hai
      Chủ động vận hành
    Ranh giới — đã đo cả hai đầu mux
      Ta sinh — NIT · SDT và BAT · EIT
      Mux sinh — PAT · PMT · CAT · TDT
      Mux đi xuyên, không sửa một byte
      Không ai sinh TOT
      Hệ khác lo DSM-CC và firmware OTA
    Hai nguồn ngang hàng
      Mỗi nguồn tự đứng được
      Không nguồn nào cần nguồn kia
      Mux nhận hai địa chỉ multicast
      Không cần giao thức cụm nào
      Đồng bộ bằng cùng một commit git
      Bộ so sánh chỉ quan sát, không chặn
    Đầu vào
      Cấu hình YAML trong git
        network.yaml
        services
        bouquets
        output.yaml
      File lịch lược đồ PSI của DVB
        Không phải XMLTV
        Không thể loại, không mô tả
        Byte mã hoá có sẵn trong nguồn
        Chỉ một ngày mỗi file
    Phần tự viết bằng Python
      YAML sang XML bảng của TSDuck
      File lịch sang section EIT
      Tự cấp event_id tất định
      Tích luỹ cửa sổ 192 giờ
      Tiêu thụ mọi dịch vụ trong file lịch
      Sinh bản vá YAML khi phát hiện lệch
      Giao diện nhập liệu ghi thẳng vào git
    TSDuck lo phần khó
      Mã hoá section và CRC-32
      Carousel theo chu kỳ
      Continuity counter và null padding
      Điều tốc CBR
      Phát UDP multicast
      eitinject tự quản version EIT
    Vận hành
      Linux · Docker host network
      Không đặt CPU quota cho container phát
      NTP có giám sát là bắt buộc
      Container phát tách khỏi nhịp deploy
      TSDuck build không kèm Dektec
    Quy tắc bất biến
      NIT version chỉ đổi khi người quyết định
      version_number rộng 5 bit — 0 đến 31, quay vòng
      EIT present-following version phải tự tăng
      Hai nguồn phải mang cùng version NIT
      Dịch vụ phải có trong 0x41 mới tồn tại
      Sinh bảng phải tất định
      Khoá liên động phải hỏng theo hướng mở
      So sánh phải làm ở mức section
    Lỗi tồn đọng đang phát sóng
      Ba linkage trỏ vào TSID không tồn tại
      Bouquet 0x6520 rỗng hoàn toàn
      26 trên 44 kênh không có EPG
      Provider name lem nhem trong SDT
```

---

## 2. Cấu trúc hai nguồn ngang hàng

Điểm cần nhìn thấy: **không có mũi tên nào nối Nguồn A với Nguồn B**. Chúng giống nhau vì cùng đọc một commit và cùng chạy một hàm thuần, không phải vì trao đổi với nhau.

```mermaid
flowchart LR
  GIT[("Cấu hình YAML<br/>trong git")]
  EPG["File lịch<br/>lược đồ PSI"]

  subgraph SA["Nguồn A"]
    direction TB
    A2["Lớp điều khiển"] --> A3["tsp · TSDuck"]
  end

  subgraph SB["Nguồn B"]
    direction TB
    B2["Lớp điều khiển"] --> B3["tsp · TSDuck"]
  end

  GIT --> A2
  GIT --> B2
  EPG --> A2
  EPG --> B2

  A3 -->|"multicast A"| MUX["ProStream 9100<br/>đi xuyên, tự chọn input"]
  B3 -->|"multicast B"| MUX
  MUX -->|"MPTS"| MOD["Điều chế DVB-S2<br/>Vinasat-1 132°E"]

  A3 -.->|"quan sát"| CMP["Bộ so sánh<br/>mức section"]
  B3 -.->|"quan sát"| CMP
  MUX -.->|"quan sát"| CMP
  CMP -.->|"báo động<br/>+ bản vá đề xuất"| GIT
```

Ở **giai đoạn chuyển tiếp**, Nguồn A là Barrowa. Nó không đọc được git và không biết Nguồn B tồn tại — nên mọi thay đổi phải áp hai nơi: commit vào git, và thao tác tay trên giao diện Barrowa. Ở **giai đoạn ổn định**, cả hai nguồn đều là hệ mới và cùng đọc một commit.

---

## 3. Đường đi của dữ liệu, trong một nguồn

```mermaid
flowchart TB
  CFG["Cấu hình YAML"] --> CTL
  EPGF["File lịch PSI<br/>theo ngày"] --> STORE["Kho lịch<br/>cửa sổ 192 giờ"] --> CTL

  CTL["Lớp điều khiển"]
  CTL -->|"bảng .xml"| INJ["inject"]
  CTL -->|"section EIT"| EIT["eitinject"]

  SRC["-I null"] --> INJ --> EIT --> REG["regulate<br/>CBR + null"] --> IP["-O ip"]
  IP --> OUT(["multicast riêng<br/>PID 16 · 17 · 18"])

  AIR["Luồng đang trên sóng"] -.->|"đọc version"| CTL
```

---

## 4. Ghi chú cho những nút không tự giải thích

| Nút | Vì sao nó ở đó |
|---|---|
| **Mux đi xuyên, không sửa một byte** | Đã đo hai đầu: 10 bảng cấu trúc — NIT, ba SDT, sáu BAT — **trùng khít từng trường kể cả version**, qua bốn bản dump trải bốn ngày. Không còn là suy luận. |
| **Không ai sinh TOT** | Mux có TDT chu kỳ 4 s mang UTC, nhưng **không bảng nào** mang `local_time_offset_descriptor`. Đầu thu hiện đúng giờ Việt Nam nhờ đâu là câu hỏi nghiệp vụ còn bỏ ngỏ. |
| **Không cần giao thức cụm nào** | Barrowa phải có discovery multicast và ba cổng riêng vì hai máy của nó ghi vào cùng một đích — chính giao thức đó đẻ ra tình trạng *config changed on both*. Ở đây mux làm việc chọn, nên cả lớp lỗi split-brain biến mất cùng giao thức. |
| **Đồng bộ bằng cùng một commit git** | Không có heartbeat giữa hai nguồn. Chúng giống nhau vì tính tất định: cùng đầu vào, cùng hàm thuần, cùng byte. |
| **Tự cấp `event_id` tất định** | Nguồn đánh số lại từ 64000 cho mỗi dịch vụ mỗi ngày. Đo trên file thật: giữ nguyên id nguồn thì **87,5 %** sự kiện trong cửa sổ 8 ngày bị nuốt. Và không được dùng bộ đếm vì hai nguồn phải ra cùng số. |
| **Tiêu thụ mọi dịch vụ trong file lịch** | Barrowa phải gán nguồn thủ công cho từng dịch vụ và bỏ quên 26 kênh. Hệ mới làm ngược lại: lấy hết, muốn loại thì ghi tường minh. |
| **So sánh phải làm ở mức section** | Bài học đắt: `tstables` mặc định chỉ xuất bảng hoàn chỉnh, nên năm bản dump đều trống phần EIT schedule dù nó có thật trên sóng ở 139 kbps. Một bộ so sánh chờ bảng hoàn chỉnh sẽ mù đúng ở chỗ chiếm 87 % tải SI. |
| **Khoá liên động phải hỏng theo hướng mở** | Không đọc được nguồn kia thì vẫn phát. Mất tham chiếu không phải bằng chứng mình sai — và nếu nguồn kia vừa chết thì đó chính là lúc mình cần phát nhất. |
| **Dịch vụ phải có trong `0x41` mới tồn tại** | Tài liệu quy tắc VTC: đầu thu chỉ lưu dịch vụ có mặt trong `service_list_descriptor` sau khi dò. Vì vậy descriptor này phải sinh tự động, không cho gõ tay. |

---

## 5. Con số — tất cả đều đo được, không phải chép từ cấu hình

| | |
|---|---|
| Mạng | `network_id` 12901 · tên `VTC` · Vinasat-1 132,0°E |
| Transport stream | 3 — **chỉ TSID 8 mang ONID 12901**, tức của VTC |
| Kênh của VTC | **64** trên TSID 8: 44 truyền hình + 20 phát thanh |
| TS mạng khác | TSID 3 (14 kênh) và TSID 1000 (10 kênh), đều ONID 1 |
| Bouquet trên sóng | 6 — `0x3622` `0x6510` `0x6520` `0x6550` `0x6604` `0x0044` |
| LCN | 87 mục, biến thể **NorDig v1** |
| PID 16 · NIT | 2,9 kbps |
| PID 17 · SDT + BAT | 18,8 kbps |
| PID 18 · EIT | **139 kbps — 86,5 % tải SI** |
| EPG phủ | **18 trên 44** kênh truyền hình |
| Độ sâu EPG | 8 ngày: `day 0..3` và `day 4..7` |

### Version đang trên sóng — giá trị gieo cho YAML

| Bảng | v | | Bảng | v |
|---|---:|---|---|---:|
| NIT | **4** | | BAT `0x3622` | **18** |
| SDT TSID 8 | **9** | | BAT `0x6510` | **26** |
| SDT TSID 3 | **12** | | BAT `0x6520` | **27** |
| SDT TSID 1000 | **19** | | BAT `0x6550` | **2** |
| | | | BAT `0x6604` | **13** |
| | | | BAT `0x0044` | **10** |

Giống hệt nhau ở cả bốn bản dump trải bốn ngày — cấu hình rất ổn định, đúng điều kiện mà mô hình đồng bộ bằng git cần.

---

## 6. Đã đo và chưa đo

Phân biệt này quan trọng: một kết luận rút từ bản đo sai cách cũng sai như đoán mò.

| Đã đo trực tiếp | Còn suy luận hoặc chưa đo |
|---|---|
| Mux đi xuyên nguyên vẹn NIT/SDT/BAT | Mux có giới hạn bitrate PID 18 không |
| Ba descriptor `0x43` khớp vector kiểm thử | Mux làm gì khi mất luồng SI đầu vào |
| LCN là NorDig v1 | Đầu thu lấy lệch giờ `+07:00` từ đâu |
| Payload linkage Irdeto `0x80` `0x82` `0x09` | `running_status` của EIT schedule trên sóng |
| EIT chỉ có `short_event_descriptor` | Cấu trúc segment của EIT schedule Barrowa đang phát |
| Mux sinh TDT, không ai sinh TOT | |
| Version của cả 10 bảng cấu trúc | |
| EPG chỉ phủ 18 trên 44 kênh | |

Ba dòng đầu cột phải đều đóng được bằng **một phép thu duy nhất**: `tstables --pid 18 --all-sections` chạy hai phút, cộng một lần rút cáp trong giờ thấp điểm.
