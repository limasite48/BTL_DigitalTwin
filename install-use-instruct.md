# HƯỚNG DẪN CÀI ĐẶT VÀ VẬN HÀNH DỰ ÁN DIGITAL TWIN

> **Đồ án môn**: Nhập môn Công nghệ Song sinh Thực - Số (Digital Twin)  
> **Cấu trúc nộp bài**: 2 module chính bao gồm **`_simReal`** (Module mô phỏng thực tế) và **`_unity/dw`** (Module giao diện 3D Digital Twin).

---

## 📋 1. Yêu cầu tiền đề (Prerequisites)

Dự án chạy tốt nhất trên hệ điều hành **Windows 10 / 11 (x64)**. Trước khi chạy dự án, máy tính cần cài đặt các công cụ sau:

1. **Docker Desktop**: Chạy hạ tầng Database (PostgreSQL), Message Broker (Mosquitto MQTT) và Cache (Redis).
   * 📥 [Tải Docker Desktop cho Windows](https://www.docker.com/products/docker-desktop/) *(Đảm bảo Docker Desktop đang mở trước khi khởi chạy hệ thống)*.
2. **Java Development Kit (JDK 21+)**: Chạy server Backend Spring Boot.
   * 📥 [Tải Eclipse Temurin JDK 21](https://adoptium.net/) hoặc Oracle OpenJDK 21+.
   * Kiểm tra bằng lệnh: `java -version`
3. **Python 3.10+ & Trình quản lý gói `uv`**: Quản lý và khởi chạy các vi dịch vụ mô phỏng Python.
   * 📥 [Tải Python 3.10+](https://www.python.org/downloads/)
   * Cài đặt `uv` bằng PowerShell:
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
     *Hoặc cài qua pip*: `pip install uv`

---

## 🏗️ 2. Tổng quan Cấu trúc Dự án

```text
BTL_DigitalTwin/
├── _simReal/                         # Module Mô phỏng Thực tế (Real System)
│   ├── iot-server/                   # Spring Boot Backend REST/MQTT Server (Java 21, Gradle)
│   ├── iot-gateway-simulate/         # IoT Gateway Service (Python - uv)
│   ├── iot-object-simulate/          # IoT Sensors & Actuators Simulator (Python - uv)
│   ├── weather-simulate/             # Weather & Solar Energy Engine (Python - uv)
│   ├── web_dashboard/                # Web Control Center Dashboard (HTML/JS/CSS, Port 8090)
│   ├── runSys.bat                    # Script khởi chạy 1-Click (Batch)
│   └── runSys.ps1                    # Script Master Orchestrator (PowerShell)
└── _unity/
    └── dw/                           # Module 3D Digital Twin (Standalone Executable)
        ├── btl-digitalTwin.exe       # File ứng dụng thực thi (Chạy không cần Unity)
        └── btl-digitalTwin_Data/     # Tài nguyên asset và dữ liệu biên dịch
```

---

## 🚀 3. Hướng dẫn Vận hành Hệ thống

### 🟢 CÁCH 1: Khởi chạy 1-Click tự động (Khuyên dùng)

Hệ thống đã tích hợp sẵn script **Master Orchestrator** tự động dựng toàn bộ Docker, cài đặt Virtual Environment cho các module Python qua `uv`, khởi chạy Spring Boot Backend và mở Web Control Center.

1. **Mở Docker Desktop** trên máy tính và chờ trạng thái Docker chuyển sang `Engine running`.
2. Mở cửa sổ Terminal (PowerShell hoặc Command Prompt) tại thư mục gốc dự án hoặc thư mục `_simReal`.
3. Chạy file batch điều khiển:
   ```cmd
   cd _simReal
   .\runSys.bat
   ```
   *(Hoặc chạy trực tiếp file PowerShell: `powershell -ExecutionPolicy Bypass -File .\runSys.ps1`)*

4. **Tự động mở trình duyệt**: Hệ thống sẽ tự động khởi động và mở trang web điều khiển tại:
   👉 **`http://localhost:8090`** (Web Control Center Dashboard)

5. **Dừng hệ thống an toàn**:
   * Tại cửa sổ console đang chạy `simReal>`, nhập lệnh: `stop` hoặc `exit`
   * Script sẽ tự động dọn dẹp tiến trình Python, Java và tắt các Docker Container an toàn.

---

### 🟡 CÁCH 2: Khởi chạy thủ công từng phần (Nếu muốn kiểm tra riêng lẻ)

Nếu không dùng script tự động `runSys.bat`, bạn có thể tự khởi chạy từng thành phần theo thứ tự sau:

#### Bước 1: Khởi động Hạ tầng Docker (Database, MQTT, Redis)
```powershell
cd _simReal/iot-server/src/main/docker/compose
docker compose up -d
```
*(Kiểm tra cổng 1883 [MQTT] và 5432 [PostgreSQL] đã hoạt động)*

#### Bước 2: Chạy Spring Boot Backend (Port 8080)
```powershell
cd _simReal/iot-server
.\gradlew.bat bootRun
```
*(Kiểm tra Healthcheck tại: `http://localhost:8080/actuator/health`)*

#### Bước 3: Chạy các Module Mô phỏng Python (Weather, Gateway, Objects)
Mở 3 cửa sổ terminal riêng cho 3 thư mục và chạy:
```powershell
# Thư mục 1: Weather Engine
cd _simReal/weather-simulate
uv run main.py

# Thư mục 2: IoT Gateway
cd _simReal/iot-gateway-simulate
uv run main.py

# Thư mục 3: IoT Sensors/Actuators
cd _simReal/iot-object-simulate
uv run main.py
```

#### Bước 4: Chạy Web Dashboard Control Center (Port 8090)
```powershell
cd _simReal/web_dashboard
uv run python server.py
```
👉 TRUY CẬP: **`http://localhost:8090`**

---

## 🎮 4. Khởi chạy Ứng dụng 3D Digital Twin (Unity Executable)

Module Digital Twin đã được biên dịch thành dạng ứng dụng thực thi (.exe) độc lập, **không yêu cầu cài đặt Unity Editor**:

1. Truy cập thư mục `_unity/dw`.
2. Nhấp đôi chuột vào file **`btl-digitalTwin.exe`** để mở giao diện 3D Digital Twin.
3. **Tương tác Thời gian thực**:
   * Giao diện 3D sẽ tự động kết nối đến Server mô phỏng đang chạy tại `localhost`.
   * Mọi sự thay đổi trên Web Control Center (`http://localhost:8090`) như bật/tắt đèn, bật/tắt AHU điều hòa, mở cửa, thời tiết mưa/nắng... sẽ lập tức phản hồi và hiển thị tương ứng trên mô hình 3D Digital Twin.

---

## ❓ 5. Xử lý Sự cố Thường gặp (Troubleshooting)

| Sự cố | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| **Lỗi `Failed to start Docker containers`** | Docker Desktop chưa được bật | Mở ứng dụng Docker Desktop trên Windows và đợi góc dưới hiển thị xanh `Engine running` trước khi chạy script. |
| **Lỗi `uv is not recognized`** | Chưa cài đặt `uv` hoặc chưa cập nhật PATH | Chạy lệnh `pip install uv` hoặc cài lại qua PowerShell Script ở Mục 1. |
| **Lỗi `Java version conflict`** | Máy đang dùng JDK cũ (< 21) | Cài đặt JDK 21+ và thiết lập biến môi trường `JAVA_HOME`. |
| **Ứng dụng 3D Unity mở lên không hiển thị dữ liệu** | Module `_simReal` chưa khởi chạy xong | Đảm bảo `runSys.bat` đã báo `SIMREAL DIGITAL TWIN SYSTEM IS ONLINE` trước khi mở `btl-digitalTwin.exe`. |
