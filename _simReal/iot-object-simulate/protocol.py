import struct
from Crypto.Cipher import AES
from config import TYPE_CODES, CODE_TO_TYPE, ZONE_CODES, CODE_TO_ZONE, AES_KEY

# Ensure AES_KEY has valid length (16, 24, or 32 bytes) by padding with zero bytes
_key_len = len(AES_KEY)
if _key_len in [16, 24, 32]:
    VALID_AES_KEY = AES_KEY
elif _key_len < 16:
    VALID_AES_KEY = AES_KEY.ljust(16, b'\x00')
elif _key_len < 24:
    VALID_AES_KEY = AES_KEY.ljust(24, b'\x00')
elif _key_len < 32:
    VALID_AES_KEY = AES_KEY.ljust(32, b'\x00')
else:
    VALID_AES_KEY = AES_KEY[:32]

tx_sequence_counter = 0

def get_next_sequence_number() -> int:
    """Increment and return the global tx sequence counter"""
    global tx_sequence_counter
    tx_sequence_counter += 1
    return tx_sequence_counter

def aes_ccm_encrypt(zone_id: int, type_code: int, seq_num: int, plaintext: bytes, key: bytes = None) -> tuple[bytes, bytes]:
    """Encrypt payload using AES-CCM mode and return (ciphertext, tag)"""
    # 13-Byte Nonce: [Zone ID (1B)][Type Code (1B)][Seq (4B)] + 7 Bytes 0x00
    nonce = struct.pack(">BBI", zone_id, type_code, seq_num) + b"\x00" * 7
    active_key = key if key is not None else VALID_AES_KEY
    cipher = AES.new(active_key, AES.MODE_CCM, nonce=nonce, mac_len=4)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return ciphertext, tag

def aes_ccm_decrypt(zone_id: int, type_code: int, seq_num: int, ciphertext: bytes, tag: bytes, key: bytes = None) -> bytes:
    """Decrypt AES-CCM frame and verify integrity (returns plaintext or None)"""
    nonce = struct.pack(">BBI", zone_id, type_code, seq_num) + b"\x00" * 7
    active_key = key if key is not None else VALID_AES_KEY
    cipher = AES.new(active_key, AES.MODE_CCM, nonce=nonce, mac_len=4)
    try:
        return cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError:
        return None

def calculate_checksum(zone_id: int, type_code: int, length: int, payload: bytes) -> int:
    """Calculate XOR Checksum for frame headers and payload"""
    chk = zone_id ^ type_code ^ length
    for b in payload:
        chk ^= b
    return chk

def wrap_uplink_frame(zone_id: int, type_code: int, payload: bytes, key: bytes = None) -> str:
    """Wrap uplink frame (Device -> Gateway) into hex string with AES-CCM security"""
    seq_num = get_next_sequence_number()
    ciphertext, tag = aes_ccm_encrypt(zone_id, type_code, seq_num, payload, key)
    # Secure Payload: [Sequence Number (4B)] + [Ciphertext] + [Tag (4B)]
    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    
    length = len(secure_payload)
    checksum = calculate_checksum(zone_id, type_code, length, secure_payload)
    frame = bytearray([0xA5, zone_id, type_code, length]) + secure_payload + bytearray([checksum, 0x5A])
    return frame.hex().upper()

def wrap_downlink_frame(zone_id: int, type_code: int, payload: bytes, key: bytes = None) -> str:
    """Wrap downlink frame (Gateway -> Device) into hex string with AES-CCM security"""
    seq_num = get_next_sequence_number()
    ciphertext, tag = aes_ccm_encrypt(zone_id, type_code, seq_num, payload, key)
    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    
    length = len(secure_payload)
    checksum = calculate_checksum(zone_id, type_code, length, secure_payload)
    frame = bytearray([0x5A, zone_id, type_code, length]) + secure_payload + bytearray([checksum, 0xA5])
    return frame.hex().upper()

def parse_downlink_frame(hex_str: str, key: bytes = None):
    """Parse downlink frame (Gateway -> Device) and decrypt AES-CCM payload"""
    try:
        hex_clean = hex_str.strip().replace(" ", "")
        data = bytes.fromhex(hex_clean)
        if len(data) < 15: # Overhead: 6B frame + 4B seq + 4B tag + min 1B payload
            return None 
        if data[0] != 0x5A or data[-1] != 0xA5:
            return None 
            
        zone_id = data[1]
        type_code = data[2]
        length = data[3]
        
        if len(data) != 6 + length:
            return None 
            
        secure_payload = data[4:4+length]
        checksum = data[4+length]
        
        if checksum != calculate_checksum(zone_id, type_code, length, secure_payload):
            return None 
            
        if len(secure_payload) < 8:
            return None
        seq_num = struct.unpack(">I", secure_payload[:4])[0]
        ciphertext = secure_payload[4:-4]
        tag = secure_payload[-4:]
        
        plaintext = aes_ccm_decrypt(zone_id, type_code, seq_num, ciphertext, tag, key)
        if plaintext is None:
            return None
            
        return {
            "zone_id": zone_id,
            "type_code": type_code,
            "payload": plaintext
        }
    except Exception:
        return None

# --- TELEMETRY ENCODERS (UPLINK) ---

def encode_dht22(zone_code: int, temp: float, humid: float, key: bytes = None) -> str:
    """Encode DHT22 temperature & humidity telemetry payload (4 Bytes)"""
    payload = struct.pack(">hH", int(temp * 10), int(humid * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["dht22"], payload, key)

def encode_mq2(zone_code: int, smoke: bool, key: bytes = None) -> str:
    """Encode MQ2 smoke alarm telemetry payload (1 Byte)"""
    payload = struct.pack(">B", 1 if smoke else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["mq2"], payload, key)

def encode_lm393(zone_code: int, light_intensity: int, key: bytes = None) -> str:
    """Encode LM393 illuminance light telemetry payload (2 Bytes)"""
    payload = struct.pack(">H", int(light_intensity))
    return wrap_uplink_frame(zone_code, TYPE_CODES["lm393"], payload, key)

def encode_mc38(zone_or_device_code: int, is_open: bool, key: bytes = None) -> str:
    """Encode MC38 door/window open contact telemetry payload (1 Byte)"""
    payload = struct.pack(">B", 1 if is_open else 0)
    return wrap_uplink_frame(zone_or_device_code, TYPE_CODES["mc38"], payload, key)

def encode_light(zone_code: int, active: bool, key: bytes = None) -> str:
    """Encode Light actuator state telemetry payload (1 Byte)"""
    payload = struct.pack(">B", 1 if active else 0)
    return wrap_uplink_frame(zone_code, TYPE_CODES["light"], payload, key)

def encode_ahu(zone_code: int, active: bool, fan_speed: int, temp_set: float, key: bytes = None) -> str:
    """Encode AHU actuator state telemetry payload (4 Bytes)"""
    payload = struct.pack(">BBh", 1 if active else 0, int(fan_speed), int(temp_set * 10))
    return wrap_uplink_frame(zone_code, TYPE_CODES["ahu"], payload, key)

def encode_curtain(window_code: int, percentage_cover: int, key: bytes = None) -> str:
    """Encode Curtain actuator state telemetry payload (1 Byte)"""
    payload = struct.pack(">B", int(percentage_cover))
    return wrap_uplink_frame(window_code, TYPE_CODES["curtain"], payload, key)

# --- COMMAND DECODERS (DOWNLINK) ---

def decode_command_payload(type_code: int, payload: bytes):
    """Decode raw command payload bytes for target device type"""
    try:
        if type_code == TYPE_CODES["light"]:
            active = struct.unpack(">B", payload)[0] == 1
            return {"active": active}
            
        elif type_code == TYPE_CODES["ahu"]:
            active_val, fan_speed, temp_set_val = struct.unpack(">BBh", payload)
            return {
                "active": active_val == 1,
                "fan_speed": fan_speed,
                "temp_set": temp_set_val / 10.0
            }
            
        elif type_code == TYPE_CODES["curtain"]:
            percentage_cover = struct.unpack(">B", payload)[0]
            return {"percentage_cover": percentage_cover}
            
        elif type_code in [TYPE_CODES["dht22"], TYPE_CODES["mq2"], TYPE_CODES["lm393"]]:
            is_poll = struct.unpack(">B", payload)[0] == 0x01
            return {"poll": is_poll}
            
    except Exception:
        pass
    return None
