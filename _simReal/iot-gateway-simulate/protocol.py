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
    """Increment and return the global sequence counter"""
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

def parse_uplink_frame(hex_str: str, key: bytes = None):
    """Parse uplink frame (Device -> Gateway) and decrypt AES-CCM payload"""
    try:
        hex_clean = hex_str.strip().replace(" ", "")
        data = bytes.fromhex(hex_clean)
        if len(data) < 7:
            print(f"[DEBUG ERR] Frame too short: {hex_str}", flush=True)
            return None
        if data[0] != 0xA5 or data[-1] != 0x5A:
            print(f"[DEBUG ERR] Invalid Start/End byte: {hex_str}", flush=True)
            return None
            
        zone_id = data[1]
        type_code = data[2]
        length = data[3]
        
        if len(data) != 6 + length:
            print(f"[DEBUG ERR] Invalid frame length: {hex_str}", flush=True)
            return None
            
        secure_payload = data[4:4+length]
        checksum = data[4+length]
        
        if checksum != calculate_checksum(zone_id, type_code, length, secure_payload):
            print(f"[DEBUG ERR] Invalid checksum: {hex_str}", flush=True)
            return None
            
        if len(secure_payload) < 8:
            print(f"\n[SECURITY ALERT] Received unencrypted packet from Zone ID 0x{zone_id:02X}, Type Code 0x{type_code:02X}!\n", flush=True)
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
    except Exception as e:
        print(f"[DEBUG ERR] Error decoding Hex packet: {e}", flush=True)
        return None

def decode_uplink_payload(type_code: int, payload: bytes):
    """Decode raw telemetry payload bytes from device"""
    try:
        if type_code == TYPE_CODES["dht22"]:
            temp_val, humid_val = struct.unpack(">hH", payload)
            return {"temp": temp_val / 10.0, "humid": humid_val / 10.0}
            
        elif type_code == TYPE_CODES["mq2"]:
            smoke = struct.unpack(">B", payload)[0] == 1
            return {"smoke": smoke}
            
        elif type_code == TYPE_CODES["lm393"]:
            light_intensity = struct.unpack(">H", payload)[0]
            return {"light_intensity": light_intensity}
            
        elif type_code == TYPE_CODES["mc38"]:
            is_open = struct.unpack(">B", payload)[0] == 1
            return {"status": "OPEN" if is_open else "CLOSED"}
            
        elif type_code == TYPE_CODES["light"]:
            active = struct.unpack(">B", payload)[0] == 1
            return {"status": "ON" if active else "OFF"}
            
        elif type_code == TYPE_CODES["ahu"]:
            active_val, fan_speed, temp_set_val = struct.unpack(">BBh", payload)
            return {
                "status": "ON" if active_val == 1 else "OFF",
                "fan_speed": fan_speed,
                "temp_set": temp_set_val / 10.0
            }
            
        elif type_code == TYPE_CODES["curtain"]:
            percentage_cover = struct.unpack(">B", payload)[0]
            return {
                "status": "CLOSED" if percentage_cover > 80 else ("OPEN" if percentage_cover < 20 else "MID"),
                "percentage_cover": percentage_cover
            }
            
    except Exception:
        pass
    return None

def wrap_downlink_frame(zone_id: int, type_code: int, payload: bytes, key: bytes = None) -> str:
    """Wrap downlink frame (Gateway -> Device) into hex string with AES-CCM security"""
    seq_num = get_next_sequence_number()
    ciphertext, tag = aes_ccm_encrypt(zone_id, type_code, seq_num, payload, key)
    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    
    length = len(secure_payload)
    checksum = calculate_checksum(zone_id, type_code, length, secure_payload)
    frame = bytearray([0x5A, zone_id, type_code, length]) + secure_payload + bytearray([checksum, 0xA5])
    return frame.hex().upper()

def encode_downlink_command(type_code: int, params: dict):
    """Encode server command into raw payload bytes for device"""
    try:
        if type_code == TYPE_CODES["light"]:
            active = 1 if params.get("active") else 0
            return struct.pack(">B", active)
            
        elif type_code == TYPE_CODES["ahu"]:
            active = 1 if params.get("active") else 0
            fan_speed = int(params.get("fan_speed", 1))
            temp_set = float(params.get("temp_set", 25.0))
            return struct.pack(">BBh", active, fan_speed, int(temp_set * 10))
            
        elif type_code == TYPE_CODES["curtain"]:
            percentage_cover = int(params.get("percentage_cover", 0))
            return struct.pack(">B", percentage_cover)
            
        elif type_code in [TYPE_CODES["dht22"], TYPE_CODES["mq2"], TYPE_CODES["lm393"]]:
            is_poll = 1 if params.get("poll") else 0
            return struct.pack(">B", is_poll)
            
    except Exception:
        pass
    return None
