# TÀI LIỆU GIỚI THIỆU TỔNG QUAN DỰ ÁN DIGITAL TWIN (BTL_DigitalTwin)

> **Môn học**: Nhập môn Công nghệ Song sinh Thực - Số (Digital Twin)  
> **Tên dự án**: Hệ thống Digital Twin Mô phỏng và Trực quan hóa Môi trường Văn phòng Thông minh (HCMC Smart Office)  
> **Phiên bản hoàn thiện**: `v1.5 Release`  
> **Cấu trúc nộp bài**: Bao gồm 2 module chính là **`_simReal`** (Module mô phỏng thực tế) và **`_unity/dw`** (Module 3D Digital Twin Executable).

---

## 📖 1. Giới thiệu Dự án & Mục tiêu

Dự án **BTL_DigitalTwin** được thiết kế nhằm xây dựng một hệ thống **Song sinh Thực - Số (Digital Twin)** hoàn chỉnh, cho phép mô phỏng vật lý thời gian thực, thu thập dữ liệu cảm biến IoT, lưu trữ & xử lý trên Backend server, và trực quan hóa tương tác 3D trên môi trường Unity Engine.

### 🎯 Mục tiêu cốt lõi:
1. **Mô phỏng Hệ thống Thực tế (`_simReal`)**: Tạo lập mô hình môi trường thực tế gồm 13 phân vùng không gian (Ban công + 12 phòng làm việc), động cơ thời tiết 5 giai đoạn, quỹ đạo thiên văn Mặt Trời NOAA, hệ thống IoT Gateway, IoT Sensors & Actuators, và Server Backend (Spring Boot 3.x, PostgreSQL, Redis, Mosquitto MQTT).
2. **Song sinh Số 3D (`_unity/dw`)**: Trực quan hóa 3D góc nhìn Drone thời gian thực, đồng bộ trạng thái môi trường, thiết bị chiếu sáng, điều hòa AHU, cửa ra vào/cửa sổ, đồng thời suy luận độc lập trạng thái thời tiết (sương mù, mưa, thời gian ngày/đêm) hoàn toàn dựa trên dữ liệu đo đạc cảm biến.
3. **Kiến trúc Độc lập (Decoupling Architecture)**: Đảm bảo mô hình 3D Digital Twin không phụ thuộc trực tiếp vào các cờ trạng thái thô của backend, mà hoạt động như một thực thể số thông minh có khả năng cảm quan và suy luận môi trường.

---

## 🏗️ 2. Kiến trúc Tổng quan Hệ thống

Hệ thống được chia làm **2 khối kiến trúc độc lập (Decoupled Architecture)** kết nối qua giao thức HTTP REST API và MQTT:

```text
  ┌──────────────────────────────────────────────────────────┐
  │         MODULE MÔ PHỎNG THỰC TẾ (*real / _simReal)       │
  │                                                          │
  │   ┌────────────────┐      ┌──────────────────────────┐   │
  │   │ Weather Engine │      │ NOAA Solar Arc Engine    │   │
  │   │ (5-Phase Model)│      │ (solar_engine.py)        │   │
  │   └───────┬────────┘      └────────────┬─────────────┘   │
  │           │                            │                 │
  │           ▼                            ▼                 │
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  IoT Gateway & Sensor Simulators (Python uv)    │   │
  │   └───────────────────────┬──────────────────────────┘   │
  │                           │ (MQTT 1883)                  │
  │                           ▼                              │
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  Spring Boot Backend Server (Java 21 / Port 8080)│   │
  │   └───────────────────────┬──────────────────────────┘   │
  │                           │ (Web Control Center : 8090)  │
  └───────────────────────────┼──────────────────────────────┘
                              │
                              │ REST GET /api/state (1Hz JSON)
                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │         MODULE DIGITAL TWIN 3D (*dw / _unity)            │
  │                                                          │
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  DigitalTwinDataManager.cs (REST Polling 1Hz)    │   │
  │   └───────────────────────┬──────────────────────────┘   │
  │                           │ Dữ liệu cảm biến thô         │
  │                           ▼                              │
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  EnvironmentPerceptionEngine.cs (Bộ suy luận)    │   │
  │   │  - NOAA Astronomical Solar Geometry Calculations │   │
  │   │  - Derivative Physics: Fog vs Rain Inference     │   │
  │   │  - Short-term Trend & 60 FPS Clock Accelerator   │   │
  │   └───────────────────────┬──────────────────────────┘   │
  │                           │ Quỹ đạo Mặt trời, Mây, Mưa   │
  │                           ▼                              │
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  EnvironmentVisualizer.cs & SimTimeHUD.cs        │   │
  │   │  - Camera-bound Rain Particle System             │   │
  │   │  - URP Exponential Squared Fog Density           │   │
  │   │  - Responsive 3D Drone Camera Flight Controller   │   │
  │   └──────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────┘
```

---

## 📦 3. Danh mục Các Module & Chức năng Chi tiết

### 3.1 Module Mô phỏng Thực tế (`_simReal`)

| Thành phần | Công nghệ | Chức năng chính |
| :--- | :--- | :--- |
| **`iot-server`** | Java 21, Spring Boot 3.x, JPA, Redis, Postgres | Backend lưu trữ và xử lý telemetry, quản lý thiết bị, cung cấp REST API chuẩn cho Client & Unity. |
| **`weather-simulate`** | Python 3.10+, `uv`, NOAA Solar Model | Động cơ thời tiết 5 giai đoạn (`CLEAR` $\to$ `CLOUDY` $\to$ `DRIZZLE` $\to$ `HEAVY RAIN` $\to$ `DISSIPATING`), tính toán quỹ đạo Mặt Trời tại TP.HCM. |
| **`iot-gateway-simulate`** | Python 3.10+, `uv` | Đóng vai trò IoT Gateway tập hợp dữ liệu cảm biến từ 13 phân vùng và gửi về Server. |
| **`iot-object-simulate`** | Python 3.10+, `uv` | Mô phỏng 13 cụm cảm biến (`DHT22`, `LM393`, `MQ2`, `MC38`) và thiết bị chấp hành (Đèn, AHU, Cửa). |
| **`web_dashboard`** | HTML5, CSS3, JS, Python HTTP Server | Giao diện Web Control Center (Port 8090) cho phép điều khiển thời tiết, bật/tắt thiết bị, xem đồ thị telemetry. |
| **`runSys.bat` / `runSys.ps1`** | PowerShell / Batch Script | Script Master Orchestrator 1-Click tự động dựng Docker, khởi chạy các vi dịch vụ và mở giao diện Web. |

---

### 3.2 Module 3D Digital Twin (`_unity/dw`)

| Thành phần C# | Vị trí File | Chức năng chính |
| :--- | :--- | :--- |
| **`btl-digitalTwin.exe`** | [`_unity/dw/btl-digitalTwin.exe`](file:///d:/_work/_hust/BTL_DigitalTwin/_unity/dw/btl-digitalTwin.exe) | Bản build Standalone chạy độc lập trên Windows x64 không cần cài Unity. |
| **`DigitalTwinDataManager`** | `Assets/_asset/_script/Core/` | Singleton chịu trách nhiệm Polling dữ liệu JSON 1Hz từ Server `http://localhost:8090/api/state`. |
| **`EnvironmentPerceptionEngine`** | `Assets/_asset/_script/Core/` | Bộ máy cảm quan môi trường suy luận góc Mặt Trời NOAA, thời tiết, và sương mù/mưa từ cảm biến `balcony`. |
| **`EnvironmentVisualizer`** | `Assets/_asset/_script/Environment/` | Trực quan hóa bầu trời URP, ánh sáng Mặt Trời, sương mù URP Exponential Squared và hệ thống hạt mưa gắn Camera. |
| **`ZoneLightActuator`** | `Assets/_asset/_script/Actuators/` | Điều khiển hệ thống đèn chiếu sáng 3D tại 12 văn phòng, hỗ trợ bật/tắt và điều chỉnh độ sáng. |
| **`DroneCameraController`** | `Assets/_asset/_script/Core/` | Điều khiển Camera 3D chuẩn 1:1 theo góc nhìn Drone (Phím WASD + Chuột), loại bỏ hoàn toàn độ trễ trôi camera. |
| **`InfoBubbleUI` & `SensorEntity`** | `Assets/_asset/_script/UI/ & Sensors/` | Thẻ hiển thị dữ liệu HD World-Space Canvas cho từng cảm biến, tự động điều chỉnh Uniform Scale và xử lý sự kiện click. |
| **`SimTimeHUD`** | `Assets/_asset/_script/UI/` | Giao diện Screen-Space Overlay hiển thị đồng hồ thời gian thực, tốc độ mô phỏng ($1\times \to 120\times$), trạng thái thời tiết suy luận và xu hướng. |

---

## 🌟 4. Các Điểm Nổi bật & Đột phá Kỹ thuật

1. **Nguyên tắc Độc lập Cảm quan (Decoupled Perception)**:
   * Module 3D Digital Twin **KHÔNG** đọc trực tiếp các cờ trạng thái thời tiết từ backend.
   * `*dw` chỉ đọc dữ liệu thô từ cảm biến ban công (`balcony.lux`, `balcony.temp`, `balcony.humid`) kết hợp mốc thời gian thực nghiệm (`sim_time`).
   * `EnvironmentPerceptionEngine` tự động tính toán góc nghiêng Mặt Trời, tỉ lệ mây che phủ, và dùng vi phân vật lý (`dTemp/dt`, `dHumid/dt`) để tự nhận biết khi nào có sương mù hay mưa rào.

2. **Khả năng Tăng tốc Thời gian & Tự làm mượt 60 FPS**:
   * Hệ thống hỗ trợ tăng tốc thời gian mô phỏng từ $1\times$ đến $120\times$.
   * Mặc dù dữ liệu từ server được gửi theo chu kỳ 1Hz ($1 \text{ giây/lần}$), Unity sử dụng thuật toán nội suy thời gian liên tục (`Update()`) để đảm bảo chuyển động của Mặt Trời và kim đồng hồ đạt độ mượt **60 FPS** tuyệt đối.

3. **Tối ưu hóa Hiệu năng Render 3D**:
   * Hệ thống hạt mưa (Rain Particle System) được neo vị trí theo `Camera.main` và giới hạn tối đa **350 hạt/giây** (Stretched Billboard), giúp duy trì tốc độ khung hình 60+ FPS mượt mà ngay cả trên các máy tính cấu hình trung bình.

4. **Đóng gói Độc lập 1-Click**:
   * Module mô phỏng được đóng gói bằng script `runSys.bat` tự động cài đặt venv Python qua `uv` và dựng Docker.
   * Module Digital Twin 3D được xuất thành tệp `.exe` chuẩn, người dùng/giảng viên chấm bài chỉ cần chạy mà không cần cài đặt bất kỳ phần mềm phức tạp nào khác.

---

## 📈 5. Tiến trình Phát triển Dự án qua các Phiên bản

* **v1.2 Release**: Hoàn thiện cầu nối dữ liệu REST API giữa `_simReal` và `_unity`, xây dựng Drone Camera Controller 1:1, thẻ thông tin Cảm biến HD World-Space InfoBubble UI.
* **v1.3 Release**: Thêm hệ thống thiết bị chấp hành 3D (Đèn `ZoneLightActuator`, Điều hòa AHU, Cửa ra vào/Cửa sổ).
* **v1.4 Release**: Đột phá với Động cơ Cảm quan Môi trường `EnvironmentPerceptionEngine`, mô hình thiên văn Mặt Trời NOAA, Động cơ thời tiết 5 giai đoạn, và hệ thống hiệu ứng 3D URP (Mưa hạt nhẹ + Sương mù Exponential Squared).
* **v1.5 Release (Hiện tại)**: Đóng gói dự án chuẩn hóa, tối ưu hóa tệp tin nộp bài, xây dựng script khởi chạy 1-Click `runSys.bat` và tài liệu kỹ thuật đầy đủ.
