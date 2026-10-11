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


def mint(role: str = "anon", tenant_id: str | None = None) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, str] = {"role": role}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
    sig = hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


# Lab tenant ids (match 00_schema.sql).
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "anon"
    tenant = sys.argv[2] if len(sys.argv) > 2 else None
    print(mint(role, tenant))
