"""Build a real, minimal APK with a valid *binary* AndroidManifest.xml.

Android compiles manifests into AXML (a binary chunk format). androguard parses
AXML, not plain XML, so tests need a genuinely encoded manifest. This module emits
a minimal-but-valid AXML for a manifest containing a package, one permission, a
debuggable application, and one exported activity — enough to exercise the analyzer.

Kept dependency-free (stdlib only) so it runs anywhere.
"""

from __future__ import annotations

import io
import struct
import zipfile

_ANDROID_URI = "http://schemas.android.com/apk/res/android"


class _StringPool:
    def __init__(self) -> None:
        self._strings: list[str] = []
        self._index: dict[str, int] = {}

    def add(self, s: str) -> int:
        if s not in self._index:
            self._index[s] = len(self._strings)
            self._strings.append(s)
        return self._index[s]

    def encode(self) -> bytes:
        # UTF-8 string data: [u16 char len][u8 byte len][bytes][0x00]; all our strings
        # are short ASCII so each length fits in a single byte.
        data = io.BytesIO()
        offsets: list[int] = []
        for s in self._strings:
            offsets.append(data.tell())
            raw = s.encode("utf-8")
            data.write(bytes([len(s)]))      # UTF-16 code-unit count (ASCII => char count)
            data.write(bytes([len(raw)]))    # byte count
            data.write(raw)
            data.write(b"\x00")
        string_data = data.getvalue()
        # Pad string data to a 4-byte boundary.
        while len(string_data) % 4 != 0:
            string_data += b"\x00"

        header_size = 28
        strings_start = header_size + len(offsets) * 4
        chunk_size = strings_start + len(string_data)

        out = io.BytesIO()
        out.write(struct.pack("<HH", 0x0001, header_size))   # type, headerSize
        out.write(struct.pack("<I", chunk_size))             # size
        out.write(struct.pack("<I", len(offsets)))           # stringCount
        out.write(struct.pack("<I", 0))                      # styleCount
        out.write(struct.pack("<I", 0x00000100))             # flags: UTF8_FLAG
        out.write(struct.pack("<I", strings_start))          # stringsStart
        out.write(struct.pack("<I", 0))                      # stylesStart
        for off in offsets:
            out.write(struct.pack("<I", off))
        out.write(string_data)
        return out.getvalue()


def _node_header(node_type: int, size: int) -> bytes:
    # ResChunk_header (type, headerSize=16, size) + lineNumber + comment(=none)
    return struct.pack("<HHIII", node_type, 16, size, 1, 0xFFFFFFFF)


def _start_ns(prefix: int, uri: int) -> bytes:
    return _node_header(0x0100, 24) + struct.pack("<ii", prefix, uri)


def _end_ns(prefix: int, uri: int) -> bytes:
    return _node_header(0x0101, 24) + struct.pack("<ii", prefix, uri)


def _attr(ns: int, name: int, value_str: int) -> bytes:
    # ns, name, rawValue, Res_value(size=8, res0=0, type=STRING(0x03), data)
    return struct.pack("<iii", ns, name, value_str) + struct.pack("<HBBi", 8, 0, 0x03, value_str)


def _start_el(name: int, attrs: list[bytes]) -> bytes:
    size = 16 + 20 + len(attrs) * 20
    body = struct.pack(
        "<iiHHHHHH",
        -1,            # ns (none)
        name,          # name
        20,            # attributeStart
        20,            # attributeSize
        len(attrs),    # attributeCount
        0, 0, 0,       # id/class/style index (none)
    )
    return _node_header(0x0102, size) + body + b"".join(attrs)


def _end_el(name: int) -> bytes:
    return _node_header(0x0103, 24) + struct.pack("<ii", -1, name)


def build_axml(
    package: str = "com.example.lab",
    permission: str = "android.permission.INTERNET",
    activity: str = "com.example.lab.MainActivity",
) -> bytes:
    sp = _StringPool()
    i_manifest = sp.add("manifest")
    i_uses = sp.add("uses-permission")
    i_app = sp.add("application")
    i_activity = sp.add("activity")
    i_package = sp.add("package")
    i_name = sp.add("name")
    i_debuggable = sp.add("debuggable")
    i_exported = sp.add("exported")
    i_prefix = sp.add("android")
    i_uri = sp.add(_ANDROID_URI)
    i_pkgval = sp.add(package)
    i_permval = sp.add(permission)
    i_true = sp.add("true")
    i_actval = sp.add(activity)

    nodes = b"".join(
        [
            _start_ns(i_prefix, i_uri),
            _start_el(i_manifest, [_attr(-1, i_package, i_pkgval)]),
            _start_el(i_uses, [_attr(i_uri, i_name, i_permval)]),
            _end_el(i_uses),
            _start_el(i_app, [_attr(i_uri, i_debuggable, i_true)]),
            _start_el(i_activity, [_attr(i_uri, i_name, i_actval), _attr(i_uri, i_exported, i_true)]),
            _end_el(i_activity),
            _end_el(i_app),
            _end_el(i_manifest),
            _end_ns(i_prefix, i_uri),
        ]
    )

    pool = sp.encode()
    total = 8 + len(pool) + len(nodes)
    header = struct.pack("<HHI", 0x0003, 8, total)  # RES_XML_TYPE, headerSize=8, size
    return header + pool + nodes


# Realistic discoverable content placed in asset files (as a Capacitor/RN-style app
# would ship). Values are synthetic. The "publishable" key is a public client key
# (NOT a secret); the service_role-looking token is the kind that WOULD be sensitive.
_ASSET_JS = """
// bundled app config (synthetic test data)
const SUPABASE_URL = "https://abcd1234test.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_AbCdEf0123456789xyzTESTvalue";
const api = "https://api.example-lab.test/v1/trips";
const insecure = "http://plaintext.example-lab.test/ping";
supabase.from("trips").select("*");
supabase.storage.from("receipts").list();
"""

_STRINGS_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
  <string name="supabase_url">https://abcd1234test.supabase.co</string>
  <string name="supabase_key">sb_publishable_AbCdEf0123456789xyzTESTvalue</string>
</resources>
"""


def build_apk(path: str, *, with_assets: bool = True) -> str:
    """Write a minimal valid APK to ``path`` and return it."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", build_axml())
        zf.writestr("classes.dex", b"dex\n035\x00" + b"\x00" * 100)
        zf.writestr("resources.arsc", b"\x02\x00\x0c\x00" + b"\x00" * 8)
        if with_assets:
            zf.writestr("assets/config.js", _ASSET_JS)
            zf.writestr("res/values/strings.xml", _STRINGS_XML)
    return path


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sample.apk"
    print(build_apk(out))
