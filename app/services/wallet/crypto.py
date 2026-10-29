"""本地卡包密钥与敏感字段加密。

Windows：优先 DPAPI（CryptProtectData）。
其它环境：AES-GCM（cryptography）+ 独立密钥文件；无安全实现时 fail-closed。
禁止使用重复密钥流 XOR。
"""

from __future__ import annotations

import base64
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


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    """返回 dpapi:... 或 aesgcm:...；无安全后端则抛错。"""
    if os.name == "nt":
        protected = _dpapi_protect(plaintext.encode("utf-8"))
        if protected is not None:
            return "dpapi:" + base64.b64encode(protected).decode("ascii")
    # AES-GCM 回退
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError(
            "无安全加密后端：Windows DPAPI 不可用且未安装 cryptography；拒绝加密真实凭据"
        ) from exc
    key = _load_or_create_key(settings)
    nonce = secrets.token_bytes(12)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return "aesgcm:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(settings: Settings, token: str) -> str:
    if token.startswith("dpapi:"):
        raw = base64.b64decode(token[6:])
        out = _dpapi_unprotect(raw)
        if out is None:
            raise ValueError("DPAPI 解密失败")
        return out.decode("utf-8")
    if token.startswith("aesgcm:"):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("缺少 cryptography，无法解密 AES-GCM 密文") from exc
        raw = base64.b64decode(token[7:])
        nonce, ct = raw[:12], raw[12:]
        key = _load_or_create_key(settings)
        pt = AESGCM(key).decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    raise ValueError("未知密文格式（拒绝不安全旧格式）")


def _dpapi_protect(data: bytes) -> bytes | None:
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        blob_in = DataBlob(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DataBlob()
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

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        blob_in = DataBlob(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DataBlob()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            return None
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return out
    except Exception:
        return None
