"""Live integration check: run the real Supabase tool against the lab, verify verdicts.

Not a unit test (needs the lab network + a running lab). Run inside a container attached
to the lab network:

    docker run --rm --network app_sentinel_lab-net -e MAIN_DATABASE_URL=x \
        -v $PWD/backend:/srv -w /srv --entrypoint python app_sentinel-api \
        tests/live_lab_check.py <anon_key>

Asserts, against whichever mode the lab is currently in, the expected verdict per table.
"""

from __future__ import annotations

import sys

from app.scope.config import ScopeConfig
from app.tools.supabase import AnonReadArgs, test_scoped_anonymous_read
from app.verify import verify_anonymous_read

LAB_URL = "http://lab-rest:3000"


def check(table: str, anon_key: str, scope: ScopeConfig) -> str:
    res = test_scoped_anonymous_read(
        AnonReadArgs(base_url=LAB_URL, table=table, anon_key=anon_key), scope
    )
    v = verify_anonymous_read(res)
    print(f"  {table:10} status={res.signal.get('http_status')} rows={res.signal.get('row_count')} "
          f"-> {v.outcome} (finding={v.is_finding})")
    return v.outcome


def main() -> None:
    anon_key = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "?"
    # Authorized scope for the lab target (the only way private IPs are allowed).
    scope = ScopeConfig(
        active_testing_allowed=True,
        authorized_hosts=["lab-rest"],
        authorized_resources=["table:trips", "table:invoices", "table:profiles"],
        allow_lab_targets=True,
    )
    print(f"== lab mode: {mode} ==")
    outcomes = {t: check(t, anon_key, scope) for t in ("trips", "invoices", "profiles")}

    # Also prove the gate blocks an unauthorized host even with a valid tool.
    blocked = ScopeConfig(active_testing_allowed=True, authorized_hosts=[], allow_lab_targets=True)
    res = test_scoped_anonymous_read(
        AnonReadArgs(base_url=LAB_URL, table="trips", anon_key=anon_key), blocked
    )
    print(f"  gate-block test -> ok={res.ok} error={res.signal.get('error')}")
    assert res.signal.get("error") == "scope:host_not_authorized", "gate must block unauthorized host"

    if mode == "broken":
        assert outcomes["trips"] == "unauthorized_access", outcomes
        assert outcomes["invoices"] == "unauthorized_access", outcomes
        assert outcomes["profiles"] in ("access_denied", "empty"), outcomes
        print("BROKEN expectations met: trips+invoices leak, profiles safe, gate blocks")
    elif mode == "correct":
        assert outcomes["trips"] in ("access_denied", "empty"), outcomes
        assert outcomes["invoices"] in ("access_denied", "empty"), outcomes
        assert outcomes["profiles"] in ("access_denied", "empty"), outcomes
        print("CORRECT expectations met: nothing leaks, gate blocks")
    print("LIVE CHECK PASSED")


if __name__ == "__main__":
    main()
