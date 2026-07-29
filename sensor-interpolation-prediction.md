# TÀI LIỆU KỸ THUẬT: CÁC CƠ CHẾ NỘI SUY, SUY LUẬN VÀ DỰ ĐOÁN TỪ DỮ LIỆU CẢM BIẾN TRONG DIGITAL TWIN

> **Tác giả**: Đội ngũ Phát triển BTL Digital Twin  
> **Áp dụng cho**: Module 3D Digital Twin (`_unity/dw`) & Module Mô phỏng (`_simReal`)  
> **Trọng tâm**: Phương pháp toán học, vi phân cảm biến, thuật toán nội suy và mô hình suy luận vật lý.

---

## 📌 1. Tổng quan về Xử lý & Cảm quan Dữ liệu Cảm biến

Trong hệ thống Digital Twin, dữ liệu đo đạc từ các cảm biến IoT (như `DHT22` đo nhiệt độ/độ ẩm, `LM393` đo cường độ ánh sáng Lux, `MQ2` đo nồng độ khí) được gửi từ Edge về Server theo chu kỳ $1\text{ Hz}$ ($1\text{ giây/lần}$).

Nếu sử dụng trực tiếp các giá trị thô này để hiển thị trên môi trường 3D:
1. Giao diện 3D sẽ bị hiện tượng giật cục (stuttering) do tốc độ làm mới của màn hình là $60\text{ FPS}$ nhưng dữ liệu cảm biến chỉ cập nhật $1\text{ FPS}$.
2. Các cờ trạng thái môi trường (như mưa, mây, sương mù) nếu phụ thuộc hoàn toàn vào cờ gửi từ Backend sẽ làm mất tính độc lập và khả năng cảm quan thực thể của mô hình Digital Twin.

Do đó, **Module 3D Digital Twin (`_unity/dw`)** được trang bị **Động cơ Cảm quan Môi trường (`EnvironmentPerceptionEngine.cs`)** nhằm thực hiện 4 nhiệm vụ kỹ thuật cốt lõi:
- **Nội suy thời gian liên tục 60 FPS** giữa các nhịp Polling 1Hz.
- **Suy luận thiên văn vị trí Mặt Trời & Cường độ bức xạ** theo mô hình NOAA.
- **Phân biệt vi phân vật lý giữa Sương mù (Fog) và Mưa rào (Rain)** từ chuỗi thời gian nhiệt-ẩm.
- **Dự đoán xu hướng biến thiên ngắn hạn** bằng hồi quy tuyến tính cửa sổ trượt.

---

## 📐 2. Cơ chế Nội suy Thời gian & Làm mượt Chuyển động (Continuous Time Interpolation)

### 2.1 Nội suy Đồng hồ Thời gian Thực nghiệm 60 FPS
Để đảm bảo Mặt Trời và kim đồng hồ trên giao diện 3D di chuyển mượt mà ở tần số $60\text{ FPS}$ ngay cả khi tốc độ mô phỏng được tăng tốc từ $1\times$ đến $120\times$, Unity cập nhật thời gian nội suy tại mỗi khung hình `Update()`:

$$\text{simTime}_{3D}(t + \Delta t) = \text{simTime}_{3D}(t) + \Delta t \times \text{simSpeed}$$

Trong đó:
* $\Delta t$ (`Time.deltaTime`): Thời gian trôi qua giữa 2 khung hình render (khoảng $0.0166\text{ giây}$ ở 60 FPS).
* $\text{simSpeed}$: Hệ số tăng tốc thời gian ($1\times, 10\times, 60\times, 120\times$).

Khi nhịp Polling $1\text{ Hz}$ mới từ Server trả về, thời gian local sẽ được hiệu chỉnh mượt (Soft-sync) để loại bỏ sai số tích lũy:

$$\text{simTime}_{3D} \leftarrow \text{Mathf.Lerp}(\text{simTime}_{3D}, \text{simTime}_{\text{server}}, 0.1)$$

---

### 2.2 Làm mượt Chuyển pha Thời tiết 5 Giai đoạn (Exponential Lerp)
Trong Động cơ Thời tiết [`weather_engine.py`](file:///d:/_work/_hust/BTL_DigitalTwin/_simReal/weather-simulate/weather_engine.py), sự chuyển pha giữa 5 trạng thái:
$$\text{CLEAR} \longrightarrow \text{CLOUDY} \longrightarrow \text{DRIZZLE} \longrightarrow \text{HEAVY RAIN} \longrightarrow \text{DISSIPATING}$$
được thực hiện bằng phương trình làm mượt mũ liên tục (Continuous Exponential Lerp) với hệ số $\alpha = 0.05$:

$$y(t + \Delta t) = y(t) + \alpha \cdot \left(y_{\text{target}} - y(t)\right)$$

* **Tỉ lệ mây che phủ (Cloud Cover)**: Nội suy liên tục giữa $15\% \leftrightarrow 90\%$.
* **Cường độ mưa (Rain Rate)**: Nội suy liên tục giữa $0.0\text{ mm/h} \leftrightarrow 20.0\text{ mm/h}$.
* **Mật độ Sương mù URP Exponential Squared Fog Density** trong Unity:
  $$\text{FogDensity}(t + \Delta t) = \text{Mathf.Lerp}(\text{FogDensity}(t), \text{TargetFogDensity}, \Delta t \times 2.0)$$

---

## ☀️ 3. Cơ chế Suy luận Thiên văn & Quang phổ Ánh sáng Mặt Trời (NOAA Solar Model)

Để xác định chính xác góc chiếu của Mặt Trời và cường độ ánh sáng tự nhiên chiếu vào ban công:

### 3.1 Tính toán Góc nâng ($\theta$) và Góc phương vị ($\phi$) Mặt Trời
Dựa trên thuật toán thiên văn NOAA với tọa độ địa lý TP.HCM ($\text{Lat} = 10.7769^\circ\text{N}$, $\text{Lon} = 106.7009^\circ\text{E}$) và mốc thời gian UTC+7:
1. Tính số ngày trong năm ($J$) và góc lệch Xích đạo Mặt Trời ($\delta$).
2. Tính góc giờ Mặt Trời ($H$) từ thời gian thực nghiệm $\text{simTime}_{3D}$.
3. Góc nâng Mặt Trời ($\theta$ - Elevation Angle):
   $$\sin(\theta) = \sin(\text{Lat}) \cdot \sin(\delta) + \cos(\text{Lat}) \cdot \cos(\delta) \cdot \cos(H)$$

---

### 3.2 Quang phổ Trời quang Theoretical Lux & Cường độ Ánh sáng 3D
Hệ thống tính toán **Khối không khí ($\text{AirMass}$)** và mức độ rọi lý thuyết khi trời không mây ($\text{ClearSkyTheoreticalLux}$):

$$\text{AirMass} = \frac{1}{\sin(\theta) + 0.50572 \cdot (\theta + 6.07995)^{-1.6364}}$$

$$\text{ClearSkyTheoreticalLux} = 1361.0 \times 0.7^{\text{AirMass}^{0.67}} \times \sin(\theta) \times 120.0 \quad (\text{Lux})$$

Từ giá trị cảm biến đo đạc thực tế tại ban công ($\text{Lux}_{\text{balcony}}$), `EnvironmentPerceptionEngine` suy luận **Hệ số Cường độ Ánh sáng Mặt Trời 3D ($\text{Sun.Int}$)**:

$$\text{Sun.Int} = \text{Clamp}\left(\frac{\text{Lux}_{\text{balcony}}}{\text{ClearSkyTheoreticalLux}}, 0.15, 1.2\right)$$

* Nếu $\text{Sun.Int} \approx 1.0$: Bầu trời trong xanh, không mây.
* Nếu $\text{Sun.Int} < 0.4$: Bầu trời u ám, mây dày đặc che phủ Mặt Trời.

---

## 🌧️ 4. Phân biệt Vi phân Vật lý: Sương Mù (Fog) vs. Mưa Rào (Rain)

Trong thực tế, cả **Sương mù** và **Mưa rào** đều làm cho độ ẩm không khí tăng cao ($> 85\%$). Nếu chỉ nhìn vào giá trị độ ẩm đơn thuần, mô hình Digital Twin không thể phân biệt được nên bật hiệu ứng sương mù hay hiệu ứng mưa 3D.

`EnvironmentPerceptionEngine.cs` giải quyết bài toán này bằng cách tính **Đạo hàm Vi phân theo Thời gian** của Nhiệt độ và Độ ẩm:

### 4.1 Phương trình Đạo hàm Vi phân Cảm biến
Đặt cửa sổ thời gian vi phân $\Delta t = 60\text{ giây}$:

$$\frac{d\text{Temp}}{dt} = \frac{\text{Temp}(t) - \text{Temp}(t - \Delta t)}{\Delta t} \quad \left(^\circ\text{C/min}\right)$$

$$\frac{d\text{Humid}}{dt} = \frac{\text{Humid}(t) - \text{Humid}(t - \Delta t)}{\Delta t} \quad \left(\%/\text{min}\right)$$

---

### 4.2 Thuật toán Phân loại Trạng thái Môi trường

```text
                  ┌─────────────────────────────────────────┐
                  │ Dữ liệu Cảm biến Balcony (DHT22)       │
                  │ Temp(t), Humid(t), dTemp/dt, dHumid/dt  │
                  └────────────────────┬────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
      ┌───────────────────────────┐         ┌───────────────────────────┐
      │  ĐỘ ẨM CAO TĨNH (SƯƠNG MÙ)│         │ ĐỘ ẨM TĂNG VỌT + GIẢM NHIỆT│
      │  - Humid = 92% - 98%      │         │  - dHumid/dt > +0.15%/min │
      │  - |dTemp/dt| <= 0.05°C   │         │  - dTemp/dt < -0.10°C/min │
      └─────────────┬─────────────┘         └─────────────┬─────────────┘
                    │                                     │
                    ▼                                     ▼
      ┌───────────────────────────┐         ┌───────────────────────────┐
      │ PerceivedState = Foggy    │         │ PerceivedState = Rainy    │
      │ -> URP Fog Density = 0.035│         │ -> Camera Rain Particles  │
      └───────────────────────────┘         └───────────────────────────┘
```

1. **Trạng thái Sương Mù (`PerceivedWeatherState.Foggy`)**:
   * **Điều kiện 1**: Độ ẩm đạt ngưỡng bão hòa hơi nước tĩnh $\text{Humid}(t) \in [92\%, 98\%]$.
   * **Điều kiện 2**: Biến thiên nhiệt độ tĩnh, không đổi $\left|\frac{d\text{Temp}}{dt}\right| \le 0.05^\circ\text{C/min}$.
   * **Bản chất vật lý**: Hơi nước ngưng tụ tĩnh trong không khí mà không có sự giải tỏa nhiệt năng của hạt mưa rơi.
   * **Phản hồi 3D**: Tăng mật độ sương mù URP Exponential Squared Fog Density lên $0.035$, tắt hạt mưa.

2. **Trạng thái Mưa Rào / Mưa To (`PerceivedWeatherState.Rainy`)**:
   * **Điều kiện 1**: Độ ẩm tăng vọt nhanh $\frac{d\text{Humid}}{dt} > 0.15 \%/\text{min}$ và duy trì trên $85\%$.
   * **Điều kiện 2**: Nhiệt độ giảm đột ngột $\frac{d\text{Temp}}{dt} < -0.10^\circ\text{C/min}$.
   * **Bản chất vật lý**: Khi hạt mưa rơi xuống, nước bốc hơi nhanh đồng thời thu nhiệt của môi trường không khí (hiệu ứng làm mát do mưa rào).
   * **Phản hồi 3D**: Bật hệ thống hạt mưa Camera-bound Rain Particle System ($350\text{ particles/sec}$), đặt độ mờ mây URP.

---

## 📈 5. Cơ chế Dự đoán Xu hướng Ngắn hạn (Short-term Predictive Trend Analysis)

Để dự đoán trạng thái thời tiết trong $5 - 10\text{ phút}$ tới, hệ thống áp dụng **Thuật toán Hồi quy Tuyến tính Cửa sổ Trượt (Sliding Window Linear Regression)** trên chuỗi $N = 10$ mẫu đo đạc gần nhất:

### 5.1 Công thức Độ dốc Tuyến tính (Linear Regression Slope)
Cho chuỗi giá trị cảm biến $(x_1, x_2, \dots, x_N)$ tại các mốc thời gian $(t_1, t_2, \dots, t_N)$:

$$m = \frac{N \sum_{i=1}^N (t_i \cdot x_i) - \left(\sum_{i=1}^N t_i\right) \cdot \left(\sum_{i=1}^N x_i\right)}{N \sum_{i=1}^N t_i^2 - \left(\sum_{i=1}^N t_i\right)^2}$$

---

### 5.2 Quy tắc Phân loại Xu hướng (`PerceivedTrend`)
* **$m > +0.15$**: Trạng thái **`WARMING` / `CLEARING`** (Nhiệt độ/Cường độ sáng đang tăng nhanh $\implies$ Trời đang quang dần).
* **$m < -0.15$**: Trạng thái **`COOLING` / `DARKENING`** (Nhiệt độ/Cường độ sáng đang giảm nhanh $\implies$ Mây dông đang kéo đến).
* **$|m| \le 0.15$**: Trạng thái **`STABLE`** (Môi trường ổn định).
* **$m < -0.30$ kèm $\frac{d\text{Humid}}{dt} > +0.20 \%/\text{min}$**: Trạng thái **`STORM_APPROACHING`** (Cảnh báo dông bão sắp xuất hiện trong 5 phút tới).

---

## 🔮 6. Định hướng Phát triển Mô hình AI & Tối ưu Năng lượng (v1.5+)

Từ các nền tảng toán học và suy luận vi phân hiện tại, mô hình Digital Twin có thể tiếp tục mở rộng các tính năng AI nâng cao:

1. **Điều khiển Tiết kiệm Năng lượng Chiếu sáng Tự động (`ZoneLightActuator` Auto-Dimming)**:
   * Sử dụng ánh sáng tự nhiên suy luận từ ban công ($\text{Lux}_{\text{balcony}}$) để tự động điều chỉnh độ sáng hệ thống đèn văn phòng 3D, đảm bảo tổng độ rọi trong phòng đạt chuẩn $300 - 500\text{ Lux}$ mà tối thiểu hóa điện năng tiêu thụ.
2. **Dự đoán Quán tính Nhiệt phòng HVAC (Thermal Inertia Prediction)**:
   * Xây dựng mô hình hồi quy dự đoán sự thay đổi nhiệt độ trong phòng khi mở/đóng cửa sổ (`MC38` sensor) kết hợp với nhiệt độ môi trường bên ngoài, giúp tối ưu hóa công suất bật/tắt điều hòa AHU.
