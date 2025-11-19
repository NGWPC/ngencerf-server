# calibration/umask_debug.py

import logging
import os
import traceback

log = logging.getLogger("umask_trap")

_real_umask = os.umask
_installed = False


def install_umask_trap():
    global _installed
    if _installed:
        return

    def logging_umask(new_mask):
        old_mask = _real_umask(new_mask)
        if new_mask != old_mask:
            log.warning(
                "[umask_diag] os.umask CHANGED from %s to %s\n%s",
                oct(old_mask), oct(new_mask),
                "".join(traceback.format_stack(limit=12)),
            )
        return old_mask

    os.umask = logging_umask
    _installed = True
    log.info("umask trap installed")
