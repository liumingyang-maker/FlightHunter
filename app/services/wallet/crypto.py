"""本地卡包密钥与敏感字段加密。

Windows：优先 DPAPI（CryptProtectData）。
其它平台/测试：data/wallet.key + scrypt + XOR-HMAC 流（仅本机演示级，日志脱敏）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from app.config import Settings


def _key_path(settings: Settings) -> Path:
    return Path(settings.project_root) / "data" / "wallet.key"


def _load_or_create_key(settings: Settings) -> bytes:
    path = _key_path(settings)
    if path.is_file():
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.hex(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _scrypt(key: bytes, salt: bytes, n: int = 2**14) -> bytes:
    return hashlib.scrypt(key, salt=salt, n=n, r=8, p=1, dklen=32)


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    """返回 v1:base64(salt|mac|cipher)。"""
    if os.name == "nt":
        protected = _dpapi_protect(plaintext.encode("utf-8"))
        if protected is not None:
            return "dpapi:" + base64.b64encode(protected).decode("ascii")
    key = _load_or_create_key(settings)
    salt = secrets.token_bytes(16)
    stream = _scrypt(key, salt)
    data = plaintext.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(data, stream * ((len(data) // 32) + 1), strict=False))
    mac = hmac.new(key, salt + cipher, hashlib.sha256).digest()
    return "v1:" + base64.b64encode(salt + mac + cipher).decode("ascii")


def decrypt_secret(settings: Settings, token: str) -> str:
    if token.startswith("dpapi:"):
        raw = base64.b64decode(token[6:])
        out = _dpapi_unprotect(raw)
        if out is None:
            raise ValueError("DPAPI 解密失败")
        return out.decode("utf-8")
    if not token.startswith("v1:"):
        raise ValueError("未知密文格式")
    raw = base64.b64decode(token[3:])
    salt, mac, cipher = raw[:16], raw[16:48], raw[48:]
    key = _load_or_create_key(settings)
    expect = hmac.new(key, salt + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expect):
        raise ValueError("MAC 校验失败")
    stream = _scrypt(key, salt)
    data = bytes(a ^ b for a, b in zip(cipher, stream * ((len(cipher) // 32) + 1), strict=False))
    return data.decode("utf-8")


def _dpapi_protect(data: bytes) -> bytes | None:
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            return None
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return out
    except Exception:
        return None


def _dpapi_unprotect(data: bytes) -> bytes | None:
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            return None
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return out
    except Exception:
        return None
