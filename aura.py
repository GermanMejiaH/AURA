from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ directory is first in sys.path to import src/aura package
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def main() -> int:
    from aura import AURA

    aura_app = AURA()
    try:
        aura_app.boot()
        aura_app.run_until_shutdown()
    except KeyboardInterrupt:
        aura_app.request_shutdown(reason="keyboard_interrupt")
    finally:
        if not aura_app.lifecycle.is_stopped:
            aura_app.shutdown(wait=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
