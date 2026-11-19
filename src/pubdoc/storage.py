"""storage.sustenaut.eu's file routes, as pubdoc uses them: upload a render
to a tenant, where it is named by its SHA-256, and fetch it back.

A token is $PUBDOC_STORAGE_TOKEN, else $GITHUB_TOKEN, else `gh auth token`:
a GitHub token that may push to the tenant's repository, which an editors
tenant takes for both, or a workflow's OpenID Connect token for reading.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class StorageError(Exception):
    pass


def token() -> str | None:
    for name in ("PUBDOC_STORAGE_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    gh = shutil.which("gh")
    if gh:
        done = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _request(request: urllib.request.Request, auth: str | None) -> bytes:
    if auth:
        request.add_header("Authorization", f"Bearer {auth}")
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:
            return answer.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise StorageError(f"{request.get_method()} {request.full_url}: {e.code} {detail}") from None
    except urllib.error.URLError as e:
        raise StorageError(f"{request.get_method()} {request.full_url}: {e.reason}") from None


def upload(base: str, tenant: str, name: str, data: bytes, label: str) -> str:
    """Store `data` in `tenant`, kept for good, and return its address.
    Refuses an answer naming any other content than `data`'s."""
    boundary = uuid.uuid4().hex
    parts = []
    for field, value in (("name", name), ("label", label[:200]), ("kept", "true")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                 "Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(f"{base}/{tenant}/files", data=b"".join(parts), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    answer = json.loads(_request(request, token()))
    if answer.get("id") != sha256(data):
        raise StorageError(f"storage stored {name} as {answer.get('id')}, not as its sha256 {sha256(data)}")
    return f"{base}{answer['url']}"


def download(url: str, expected: str) -> bytes:
    """The file at `url`, refused unless its SHA-256 is `expected`."""
    data = _request(urllib.request.Request(url), token())
    if sha256(data) != expected:
        raise StorageError(f"{url} is not the file recorded: its sha256 is {sha256(data)}, not {expected}")
    return data


def save(url: str, expected: str, target: Path) -> Path:
    target.write_bytes(download(url, expected))
    return target
