"""Protect model API keys at rest.

Windows uses DPAPI (user-scoped). Other platforms wrap with a 0o600 key file
next to config.json so a copied JSON blob is not usable on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path

from office_agent.paths import app_data_dir, write_private_bytes

SEAL_PREFIX = "oa1:"
_WRAP_KIND = "wrap:"
_DPAPI_KIND = "dpapi:"
_WRAP_KEY_NAME = "secrets.key"
_NONCE_SIZE = 16
_MAC_SIZE = 32


def wrapping_key_path() -> Path:
    return app_data_dir() / _WRAP_KEY_NAME


def seal_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    raw = plaintext.encode("utf-8")
    if os.name == "nt":
        try:
            blob = _dpapi_protect(raw)
            return SEAL_PREFIX + _DPAPI_KIND + _b64(blob)
        except OSError:
            pass
    return SEAL_PREFIX + _WRAP_KIND + _b64(_wrap_encrypt(raw))


def unseal_secret(token: str) -> str:
    if not token:
        return ""
    if not token.startswith(SEAL_PREFIX):
        return token
    rest = token[len(SEAL_PREFIX) :]
    if rest.startswith(_DPAPI_KIND):
        blob = _b64d(rest[len(_DPAPI_KIND) :])
        return _dpapi_unprotect(blob).decode("utf-8")
    if rest.startswith(_WRAP_KIND):
        blob = _b64d(rest[len(_WRAP_KIND) :])
        return _wrap_decrypt(blob).decode("utf-8")
    raise ValueError("unknown sealed secret format")


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return urlsafe_b64decode(text + pad)


def _load_or_create_wrap_key() -> bytes:
    path = wrapping_key_path()
    if path.is_file():
        key = path.read_bytes()
        if len(key) == 32:
            return key
    key = secrets.token_bytes(32)
    write_private_bytes(path, key)
    return key


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _wrap_encrypt(plain: bytes) -> bytes:
    key = _load_or_create_wrap_key()
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain)), strict=True))
    mac = hmac.new(key, b"oa1-mac" + nonce + ct, hashlib.sha256).digest()
    return nonce + mac + ct


def _wrap_decrypt(blob: bytes) -> bytes:
    if len(blob) < _NONCE_SIZE + _MAC_SIZE:
        raise ValueError("secret unwrap failed")
    key = _load_or_create_wrap_key()
    nonce = blob[:_NONCE_SIZE]
    mac = blob[_NONCE_SIZE : _NONCE_SIZE + _MAC_SIZE]
    ct = blob[_NONCE_SIZE + _MAC_SIZE :]
    expected = hmac.new(key, b"oa1-mac" + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("secret unwrap failed")
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct)), strict=True))


def _dpapi_protect(data: bytes) -> bytes:
    return _dpapi_crypt(data, protect=True)


def _dpapi_unprotect(data: bytes) -> bytes:
    return _dpapi_crypt(data, protect=False)


def _dpapi_crypt(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise OSError("DPAPI is only available on Windows")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ui_forbidden = 0x01
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        ui_forbidden,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("DPAPI operation failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
