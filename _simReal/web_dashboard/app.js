// SimReal Web Control Dashboard App Engine

let currentState = null;

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (res.ok) {
      currentState = await res.json();
      renderDashboard(currentState);
    }
  } catch (err) {
    console.error("Fetch state error:", err);
  }
}

async function sendCmd(payload) {
  try {
    const res = await fetch("/api/cmd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      fetchState();
    }
  } catch (err) {
    console.error("Send command error:", err);
  }
}

function renderDashboard(state) {
  if (!state) return;

  // 1. Weather Rendering
  const w = state.weather || {};
  document.getElementById("sim-time-text").textContent = w.sim_time || "N/A";
  document.getElementById("val-outdoor-temp-humid").textContent = `${(w.temp || 0).toFixed(1)} °C / ${(w.humid || 0).toFixed(1)} %`;
  document.getElementById("val-outdoor-cloud-rain").textContent = `${(w.cloud_cover_pct || 0).toFixed(1)} % / ${(w.rain_intensity_mmh || w.rain_mmh || 0).toFixed(1)} mm/h`;
  document.getElementById("val-outdoor-lux").textContent = `${(w.lux || 0).toLocaleString()} Lux`;
  document.getElementById("val-sun-pos").textContent = `${(w.elevation || 0).toFixed(1)}° / ${(w.azimuth || 0).toFixed(1)}°`;

  if (w.speed !== undefined) {
    const spdVal = document.getElementById("speed-val");
    const spdInput = document.getElementById("speed-input");
    if (spdVal) spdVal.textContent = `${w.speed}x`;
    if (spdInput && document.activeElement !== spdInput && !spdInput.value) {
      spdInput.placeholder = w.speed.toString();
    }
  }

  const rainRate = w.rain_intensity_mmh || w.rain_mmh || 0;
  const cloudCover = w.cloud_cover_pct || 0;
  const weatherMode = (w.weather_mode || "clear").toLowerCase();

  let phaseText = "WEATHER: CLEAR ☀️";
  let phaseIcon = "☀️";
  if (weatherMode === "fog" || (cloudCover >= 90.0 && rainRate < 1.0)) {
    phaseText = "WEATHER: FOGGY 🌫️";
    phaseIcon = "🌫️";
  } else if (rainRate >= 10.0) {
    phaseText = "WEATHER: HEAVY RAIN ⛈️";
    phaseIcon = "⛈️";
  } else if (rainRate >= 2.0) {
    phaseText = "WEATHER: DRIZZLE 🌧️";
    phaseIcon = "🌧️";
  } else if (cloudCover >= 50.0) {
    phaseText = "WEATHER: CLOUDY ⛅";
    phaseIcon = "⛅";
  }

  const btnClear = document.getElementById("btn-mode-clear");
  const btnFog = document.getElementById("btn-mode-fog");
  const btnRain = document.getElementById("btn-mode-rain");
  if (btnClear) btnClear.classList.toggle("active", weatherMode === "clear");
  if (btnFog) btnFog.classList.toggle("active", weatherMode === "fog");
  if (btnRain) btnRain.classList.toggle("active", weatherMode === "rain" || w.rain_state === 1 || rainRate > 1.0);

  const txtElem = document.getElementById("weather-rain-text");
  if (txtElem) txtElem.textContent = phaseText;

  const weatherBadge = document.getElementById("weather-rain-badge");
  if (weatherBadge) {
    const iconSpan = weatherBadge.querySelector(".icon");
    if (iconSpan) iconSpan.textContent = phaseIcon;
    if (w.rain_state === 1 || rainRate > 1.0) {
      weatherBadge.classList.add("raining");
    } else {
      weatherBadge.classList.remove("raining");
    }
  }

  // 2. Gateway Rendering
  const g = state.gateway || {};
  const isOnline = g.network_connected !== false;
  document.getElementById("gw-conn-text").textContent = isOnline ? "GATEWAY: ONLINE" : "GATEWAY: OFFLINE";
  document.getElementById("stat-rx").textContent = g.rx_count || 0;
  document.getElementById("btn-toggle-network").textContent = isOnline ? "🌐 Simulate Network Outage (OFFLINE)" : "🟢 Restore Gateway Connection (ONLINE)";

  // 3. 13 Zones Rendering
  const zonesContainer = document.getElementById("zones-container");
  const zones = state.zones || {};
  
  let zonesHtml = "";
  for (const [zName, zData] of Object.entries(zones)) {
    const isBalcony = (zName === "balcony");
    const lightOn = zData.light === "ON";
    const ahu = zData.ahu || {};
    const ahuOn = ahu.status === "ON";
    const fanSpeed = ahu.fan_speed || 1;
    const tempSet = ahu.temp_set || 25.0;

    let controlsContent = "";
    if (isBalcony) {
      controlsContent = `
        <div class="balcony-badge">
          🌿 Outdoor Zone &bull; Natural Atmosphere Engine
        </div>
      `;
    } else {
      controlsContent = `
        <div class="zone-controls">
          <button class="btn-toggle ${lightOn ? 'active' : ''}" onclick="toggleLight('${zName}', ${!lightOn})">
            💡 Light: ${lightOn ? 'ON' : 'OFF'}
          </button>
          <button class="btn-toggle ${ahuOn ? 'active' : ''}" onclick="toggleAhu('${zName}', ${!ahuOn})">
            ❄️ AHU: ${ahuOn ? 'ON' : 'OFF'}
          </button>
        </div>
        <div class="ahu-sub-panel ${ahuOn ? 'active' : ''}">
          <div class="ahu-row">
            <span class="sub-label">Fan Speed:</span>
            <div class="spd-pills">
              <button class="spd-btn ${fanSpeed === 1 ? 'active' : ''}" onclick="setAhuSpeed('${zName}', 1)">1</button>
              <button class="spd-btn ${fanSpeed === 2 ? 'active' : ''}" onclick="setAhuSpeed('${zName}', 2)">2</button>
              <button class="spd-btn ${fanSpeed === 3 ? 'active' : ''}" onclick="setAhuSpeed('${zName}', 3)">3</button>
            </div>
          </div>
          <div class="ahu-row">
            <span class="sub-label">Target Temp:</span>
            <div class="temp-stepper">
              <button class="step-btn" onclick="changeAhuTemp('${zName}', -1.0)">-</button>
              <span class="temp-val">${tempSet.toFixed(1)}°C</span>
              <button class="step-btn" onclick="changeAhuTemp('${zName}', 1.0)">+</button>
            </div>
          </div>
        </div>
      `;
    }

    zonesHtml += `
      <div class="zone-card ${isBalcony ? 'balcony-highlight' : ''}">
        <div class="zone-title">
          <span>${zName.replace('_', ' ')} ${isBalcony ? '🌿' : ''}</span>
          <span style="font-size:0.7rem; color:${zData.smoke ? '#ef4444' : '#10b981'}">
            ${zData.smoke ? '🔥 SMOKE' : 'OK'}
          </span>
        </div>
        <div class="zone-metrics">
          <span>Temp: <strong>${(zData.temp || 0).toFixed(1)}°C</strong></span>
          <span>Humid: <strong>${(zData.humid || 0).toFixed(1)}%</strong></span>
          <span>Light: <strong>${zData.lux || 0} Lux</strong></span>
        </div>
        ${controlsContent}
      </div>
    `;
  }
  zonesContainer.innerHTML = zonesHtml;

  // 4. Doors Rendering
  const doorsContainer = document.getElementById("doors-container");
  const doors = state.doors || {};
  let doorsHtml = "";
  for (const [dId, dData] of Object.entries(doors)) {
    const isOpen = dData.status === "OPEN";
    doorsHtml += `
      <div class="item-control-box">
        <span>${dId.toUpperCase()}</span>
        <button class="btn-toggle ${isOpen ? 'active' : ''}" onclick="toggleDoor('${dId}', ${!isOpen})">
          ${isOpen ? '🔓 OPEN' : '🔒 CLOSED'}
        </button>
      </div>
    `;
  }
  doorsContainer.innerHTML = doorsHtml;

  // 5. Windows Rendering
  const windowsContainer = document.getElementById("windows-container");
  const windows = state.windows || {};
  let windowsHtml = "";
  for (const [wId, wData] of Object.entries(windows)) {
    const isOpen = wData.status === "OPEN";
    const curtainPct = wData.curtain_pct !== undefined ? wData.curtain_pct : 100;
    windowsHtml += `
      <div class="item-control-box window-box">
        <div class="win-header">
          <span>${wId.toUpperCase()}</span>
          <button class="btn-toggle ${isOpen ? 'active' : ''}" onclick="toggleWindow('${wId}', ${!isOpen})">
            ${isOpen ? '🪟 OPEN' : '🪟 CLOSED'}
          </button>
        </div>
        <div class="curtain-row">
          <span class="sub-label">Curtain (${curtainPct}%):</span>
          <input type="range" class="curtain-slider" min="0" max="100" value="${curtainPct}" onchange="setCurtain('${wId}', this.value)">
        </div>
      </div>
    `;
  }
  windowsContainer.innerHTML = windowsHtml;
}

// Global Interaction Handlers
window.toggleLight = function(zone, active) {
  sendCmd({ domain: "object", command: "light", zone: zone, active: active });
};

window.toggleAhu = function(zone, active) {
  const zData = (currentState && currentState.zones && currentState.zones[zone]) || {};
  const ahu = zData.ahu || {};
  const spd = ahu.fan_speed || 1;
  const tset = ahu.temp_set || 25.0;
  sendCmd({ domain: "object", command: "ahu", zone: zone, active: active, fan_speed: spd, temp_set: tset });
};

window.setAhuSpeed = function(zone, speed) {
  const zData = (currentState && currentState.zones && currentState.zones[zone]) || {};
  const ahu = zData.ahu || {};
  const isPowerOn = ahu.status === "ON";
  const tset = ahu.temp_set || 25.0;
  sendCmd({ domain: "object", command: "ahu", zone: zone, active: isPowerOn, fan_speed: speed, temp_set: tset });
};

window.changeAhuTemp = function(zone, delta) {
  const zData = (currentState && currentState.zones && currentState.zones[zone]) || {};
  const ahu = zData.ahu || {};
  const isPowerOn = ahu.status === "ON";
  const spd = ahu.fan_speed || 1;
  let newTemp = (ahu.temp_set || 25.0) + delta;
  newTemp = Math.max(16.0, Math.min(30.0, Math.round(newTemp * 10) / 10));
  sendCmd({ domain: "object", command: "ahu", zone: zone, active: isPowerOn, fan_speed: spd, temp_set: newTemp });
};

window.toggleDoor = function(doorId, isOpen) {
  sendCmd({ domain: "object", command: "door", door_id: doorId, is_open: isOpen });
};

window.toggleWindow = function(wdId, isOpen) {
  sendCmd({ domain: "object", command: "window", wd_id: wdId, is_open: isOpen });
};

window.setCurtain = function(wdId, pct) {
  sendCmd({ domain: "object", command: "curtain", wd_id: wdId, pct: parseInt(pct) });
};

window.setWeatherMode = function(mode) {
  sendCmd({ domain: "weather", command: "mode", value: mode });
};

document.getElementById("btn-toggle-network").addEventListener("click", () => {
  const isCurrentlyOnline = currentState && currentState.gateway && currentState.gateway.network_connected !== false;
  sendCmd({ domain: "gateway", command: "network", state: isCurrentlyOnline ? "off" : "on" });
});

const btnSetSpeed = document.getElementById("btn-set-speed");
if (btnSetSpeed) {
  btnSetSpeed.addEventListener("click", () => {
    const inputVal = document.getElementById("speed-input").value.trim();
    if (inputVal && !isNaN(inputVal)) {
      const spd = parseFloat(inputVal);
      document.getElementById("speed-val").textContent = `${spd}x`;
      sendCmd({ domain: "weather", command: "speed", value: spd });
      document.getElementById("speed-input").value = "";
    }
  });
}

document.getElementById("btn-set-time").addEventListener("click", () => {
  const val = document.getElementById("time-input").value.trim();
  if (val) {
    sendCmd({ domain: "weather", command: "settime", value: val });
  }
});

// Initial Fetch & Interval Polling (1 sec)
fetchState();
setInterval(fetchState, 1000);
