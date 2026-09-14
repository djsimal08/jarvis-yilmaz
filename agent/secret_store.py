from __future__ import annotations

import os


TARGET_PREFIX = "JarvisYilmaz"


def set_secret(name: str, value: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Güvenli anahtar deposu yalnızca Windows'ta kullanılabilir.")
    import win32cred

    target = f"{TARGET_PREFIX}/{name}"
    win32cred.CredWrite(
        {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "CredentialBlob": value,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            "UserName": "JARVIS",
        },
        0,
    )


def get_secret(name: str) -> str | None:
    if os.name != "nt":
        return None
    import pywintypes
    import win32cred

    try:
        credential = win32cred.CredRead(
            f"{TARGET_PREFIX}/{name}", win32cred.CRED_TYPE_GENERIC, 0
        )
    except pywintypes.error:
        return None
    blob = credential.get("CredentialBlob", b"")
    return blob.decode("utf-16-le") if isinstance(blob, bytes) else str(blob)


def delete_secret(name: str) -> None:
    if os.name != "nt":
        return
    import pywintypes
    import win32cred

    try:
        win32cred.CredDelete(
            f"{TARGET_PREFIX}/{name}", win32cred.CRED_TYPE_GENERIC, 0
        )
    except pywintypes.error:
        pass
