from __future__ import annotations

import pytest

from aura.core.aura import AURA, AURABootOptions
from aura.modules.base import BaseModule


class FailingBootModule(BaseModule):
    name = "failing-boot-mod"
    required = True

    def on_initialize(self) -> None:
        raise RuntimeError("Module initialize failed during boot")


def test_aura_boot_failure_rollback():
    options = AURABootOptions(
        auto_discover_modules=False,
        module_classes=(FailingBootModule,),
    )
    aura = AURA(options=options)

    with pytest.raises(RuntimeError, match="Required module failed to initialize"):
        aura.boot()

    assert aura.is_booted is False
    assert aura.lifecycle.is_stopped is True
