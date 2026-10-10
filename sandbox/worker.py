"""Sandbox worker placeholder (foundation).

Proves the isolated container runs. In step 2 this becomes a Procrastinate worker
bound to sandbox-db that runs androguard + JADX. It has no internet egress and no
credentials by design (ADR-005).
"""

from __future__ import annotations

import json
import time


def main() -> None:
    print(json.dumps({"level": "INFO", "logger": "sandbox", "message": "sandbox worker alive"}))
    while True:
        time.sleep(30)
        print(
            json.dumps(
                {"level": "INFO", "logger": "sandbox", "message": "sandbox heartbeat (idle)"}
            )
        )


if __name__ == "__main__":
    main()
