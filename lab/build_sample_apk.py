#!/usr/bin/env python3
"""Build the lab's sample APK: a synthetic Android app whose embedded config points at
the local lab backend (URL + anon key + table references).

The agent will discover these from the APK and (only within an authorized scope) test
the anonymous-read behaviour against the lab. The endpoint is the lab's in-cluster
address (`http://lab-rest:3000`), which the agent reaches over the Docker network.

Usage: python build_sample_apk.py [output.apk]
"""

from __future__ import annotations

import pathlib
import sys

# Reuse the binary-AXML APK builder from the backend test helpers.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "tests"))
from make_apk import build_apk  # noqa: E402

from mint_anon_key import mint  # noqa: E402  (same dir)

# In-cluster endpoints the containerized agent uses; the anon key mirrors a Supabase
# legacy anon key (role-scoped JWT). All lab-only. One app points at all three backends
# so a single upload exercises every check module (Supabase, Firebase, generic REST).
LAB_URL = "http://lab-rest:3000"
LAB_ANON_KEY = mint("anon")
LAB_TABLES = ("trips", "invoices", "profiles")
LAB_FIREBASE = "http://firebase-lab:9000"
LAB_REST = "http://restapi-lab:8080/api/orders"


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "sample-lab-app.apk"
    build_apk(out, supabase_url=LAB_URL, supabase_key=LAB_ANON_KEY, tables=LAB_TABLES,
              firebase_url=LAB_FIREBASE, rest_url=LAB_REST)
    print(out)


if __name__ == "__main__":
    main()
