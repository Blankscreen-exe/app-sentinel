#!/usr/bin/env python3
"""Mint the lab's anonymous API key: a JWT {"role":"anon"} signed with the lab secret.

This mirrors a Supabase legacy anon key (a role-scoped JWT). Lab-only and public by
design. Stdlib only (HMAC-SHA256), no dependencies.

Usage: python mint_anon_key.py [authenticated]
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys

SECRET = "lab_jwt_secret_change_me_0123456789_abcdef"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def mint(role: str = "anon") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"role": role}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
    sig = hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "anon"
    print(mint(role))
