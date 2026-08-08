from __future__ import annotations

import sys


def main() -> int:
    from aura import AURA

    aura = AURA()
    try:
        aura.boot()
        aura.run_until_shutdown()
    except KeyboardInterrupt:
        aura.request_shutdown(reason="keyboard_interrupt")
    finally:
        if not aura.lifecycle.is_stopped:
            aura.shutdown(wait=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
