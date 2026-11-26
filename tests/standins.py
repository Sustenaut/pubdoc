"""Stand-ins for what pubdoc's versions drive: publet's `pub`, storage's
file routes, and poppler's pdfinfo, pdftotext and pdftoppm.

The `pub` stand-in keeps a corpus the way pub does, as far as pubdoc sees
it: publish writes each claim of a publet's source as an object named by
its SHA-256, records them in corpus.lock with the corpus's key, and signs
the generation (here, a digest of its members under the key); corpus
status, run with the corpus as a parent, checks every object's hash and
that signature; read prints an object. It refuses to publish without
.publet/signing.key, as pub does.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUB = r'''#!PYTHON
import base64, hashlib, json, os, sys
from pathlib import Path

with open(os.environ["PUBDOC_TEST_LOG"], "a") as log:
    log.write(f"pub|{os.getcwd()}|{' '.join(sys.argv[1:])}\n")

def cid(data):
    return "pub:sha2-256:" + base64.b32encode(hashlib.sha256(data).digest()).decode().lower().rstrip("=")

def key_object(secret):
    """A key's object, as pub makes it: from the secret's public half (here
    its hash), never the secret; the key is this object's identifier."""
    return json.dumps({"type": "key", "pubkey": hashlib.sha256(secret).hexdigest()}).encode()


def key_of(secret):
    return cid(key_object(secret))


def file_of(c):
    return c.replace(":", "_") + ".cbor"

def signature(key, members):
    return hashlib.sha256((key + "".join(sorted(members))).encode()).hexdigest()

args = sys.argv[1:]
here = Path.cwd()

def set_author(value):
    (here / ".publet").mkdir(exist_ok=True)
    (here / ".publet" / "config").write_text(f"author={value}\n")

if args == ["--version"]:
    print(os.environ.get("PUBDOC_TEST_PUB_VERSION", "pub 0.4.0"))
elif args == ["init"]:
    set_author("pub:sha2-256:placeholder")
elif args == ["corpus", "init"]:
    (here / "corpus.json").write_text('{"name": "corpus", "label": "corpus", "bound": 67108864, "parents": []}\n')
    set_author("pub:sha2-256:placeholder")
elif args[:2] == ["sign", "--generate-key"]:
    key = here / ".publet" / "signing.key"
    if key.exists():
        sys.exit(f"{key} already exists")
    key.write_text(os.urandom(32).hex() + "\n")
    set_author(key_of(key.read_bytes()))
    print(f"key      {key_of(key.read_bytes())}")
elif args[:2] == ["sign", "--restore-key"]:
    key = here / ".publet" / "signing.key"
    if not key.is_file():
        sys.exit("nothing to restore")
    made = key_of(key.read_bytes())
    expect = next((a.split("=", 1)[1] for a in args if a.startswith("--expect=")), None)
    committed = expect and (here / "objects" / file_of(expect)).is_file()
    if not committed and not any(a.startswith("--created=") for a in args):
        sys.exit("--created is required: the instant the key was made at")
    for arg in args:
        if arg.startswith("--expect=") and arg.split("=", 1)[1] != made:
            sys.exit(f"the secret is the key {made}, not {arg.split('=', 1)[1]}; nothing was changed")
    set_author(made)
    print(f"key      {made}")
elif args[:1] == ["build"]:
    for source in sorted(here.glob("publets/*/publet.json")):
        if "tag" not in json.loads(source.read_text()):
            sys.exit(f"{source}: `tag` is required")
    print("drafts built")
elif args[:1] == ["publish"]:
    key_file = here / ".publet" / "signing.key"
    if not key_file.is_file():
        sys.exit(f"no signing key at {key_file}")
    key = key_of(key_file.read_bytes())
    lock_path = here / "corpus.lock"
    lock = json.loads(lock_path.read_text()) if lock_path.is_file() else {"corpus": {"key": key}, "publets": []}
    slug = args[1]
    source = json.loads((here / "publets" / slug / "publet.json").read_text())
    (here / "objects").mkdir(exist_ok=True)
    # As pub does at a corpus's first publish: its key object is committed.
    (here / "objects" / file_of(key)).write_bytes(key_object(key_file.read_bytes()))
    rows = [r for r in lock["publets"] if r["slug"].split("#")[0] != slug]
    for name, claim in source["claims"].items():
        data = json.dumps({"author": key, "body": claim, "type": "claim.prose"}, sort_keys=True).encode()
        (here / "objects" / file_of(cid(data))).write_bytes(data)
        rows.append({"slug": f"{slug}#{name}", "cid": cid(data)})
    rows.append({"slug": slug, "tag": source["tag"], "cid": cid(json.dumps(source).encode())})
    members = sorted(p.name for p in (here / "objects").glob("*.cbor"))
    index = lock["corpus"].get("generation", {}).get("index", -1) + 1
    generation = json.dumps({"members": members, "key": key, "index": index,
                             "signature": signature(key, members)}).encode()
    (here / "generation.json").write_bytes(generation)
    lock["corpus"] = {"key": key, "generation": {"index": index, "cid": cid(generation)}}
    lock["publets"] = rows
    lock_path.write_text(json.dumps(lock, indent=2))
    print(f"published {slug}")
elif args[:1] == ["read"]:
    target = args[-1]
    path = here / "objects" / file_of(target)
    if not path.is_file():
        sys.exit(f"not in objects: {target}")
    data = path.read_bytes()
    if cid(data) != target:
        sys.exit(f"{path} no longer hashes to {target}")
    print(json.dumps({"cid": target, "mode": "dir", "object": json.loads(data)}))
elif args[:2] == ["corpus", "status"]:
    parent = Path(json.loads((here / "corpus.json").read_text())["parents"][0]["path"])
    generation = json.loads((parent / "generation.json").read_text())
    for name in generation["members"]:
        data = (parent / "objects" / name).read_bytes()
        if file_of(cid(data)) != name:
            sys.exit(f"parent: {name} does not hash to its name")
    if generation["signature"] != signature(generation["key"], generation["members"]):
        sys.exit("parent: the generation's signature does not verify")
    print("verify  not built yet")
else:
    sys.exit(f"the pub stand-in does not do: {' '.join(args)}")
'''

# pubsec: logs what it was asked, and backs nothing up.
PUBSEC = """#!/bin/sh
echo "pubsec|$PWD|$*" >> "$PUBDOC_TEST_LOG"
"""

# pdfinfo, pdftotext and pdftoppm on a "PDF" that is lines of text: each
# line starting "page" is a page; its text is the rest of the line, and its
# picture a 4x1 PGM of the line's first four characters.
POPPLER = {
    "pdfinfo": 'echo "Pages: $(grep -c "^page" "$1")"\n',
    "pdftotext": 'grep "^page" "$1" | cut -d" " -f2-\n',
    "pdftoppm": ('pdf="$4"; prefix="$5"; n=0\n'
                 'grep "^page" "$pdf" | while IFS= read -r line; do n=$((n+1));'
                 ' printf "P5\\n4 1\\n255\\n%s" "$(printf %s "$line" | cut -c10-13)" > "$prefix-$n.pgm"; done\n'),
}


class Storage:
    """storage's file routes in memory: POST /<tenant>/files, GET
    /<tenant>/f/<id>/<name>, each needing the bearer token."""

    TOKEN = "test-token"

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.requests = 0
        storage = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def authorized(self):
                storage.requests += 1
                # As storage's edge does: urllib's own agent is refused.
                if self.headers.get("User-Agent", "").startswith("Python-urllib"):
                    self.answer(403, b"error code: 1010")
                    return False
                if self.headers.get("Authorization") != f"Bearer {Storage.TOKEN}":
                    self.answer(401, {"error": "a token is needed"})
                    return False
                return True

            def answer(self, status, body):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if not self.authorized():
                    return
                tenant = self.path.strip("/").split("/")[0]
                body = self.rfile.read(int(self.headers["Content-Length"]))
                message = BytesParser(policy=HTTP).parsebytes(
                    f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body)
                fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                          for part in message.iter_parts()}
                data, name = fields["file"], fields["name"].decode()
                ident = hashlib.sha256(data).hexdigest()
                storage.files[ident] = data
                self.answer(200, {"id": ident, "name": name, "url": f"/{tenant}/f/{ident}/{name}",
                                  "type": "application/pdf", "size": len(data), "label": "",
                                  "subject": "", "kept": fields.get("kept") == b"true"})

            def do_GET(self):
                if not self.authorized():
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[1] == "f" and parts[2] in storage.files:
                    self.answer(200, storage.files[parts[2]])
                else:
                    self.answer(404, {"error": "no such file"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def cid_of(data: bytes) -> str:
    return "pub:sha2-256:" + base64.b32encode(hashlib.sha256(data).digest()).decode().lower().rstrip("=")
