# Module Mô phỏng Mặt trời & Thời tiết (`_simReal/weather-simulate`)

Module đóng vai trò **Ground Truth Engine** cho Tầng Thực tại Vật lý (`_simReal`). Module tính toán vị trí mặt trời (Azimuth, Elevation), cường độ bức xạ ánh sáng (Lux), nhiệt độ, độ ẩm ngoài trời và trạng thái mưa/tạnh ráo, sau đó phát sóng lên MQTT Broker qua IPC Topic `simreal/weather/state`.

---

## 🚀 Hướng dẫn Khởi chạy

Sử dụng công cụ `uv`:

```bash
# Chạy với tham số mặc định
uv run main.py

# Chạy tăng tốc thời gian (ví dụ 60x: 1s thực = 1 phút giả lập)
uv run main.py --speed 60

# Bắt đầu giả lập với thời tiết mưa từ 5:30 sáng
uv run main.py --start-time 2026-07-01T05:30:00 --rain
```

---

## 🎮 Phím tắt Điều khiển Console

Khi script đang chạy trên Terminal/Console:
- **`r`**: Bật/tắt hiệu ứng Mưa (Toggle Rain ON / OFF).
- **`+`**: Tăng tốc độ thời gian giả lập (1x -> 2x -> 4x -> 60x...).
- **`-`**: Giảm tốc độ thời gian giả lập.
- **`q`**: Thoát chương trình an toàn.
