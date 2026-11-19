"""Browser CI collects this case; make check collects the same test directly."""

from tests.test_output_download import (
    test_download_disables_after_recovery_blocks_output as _case,
)


def test_download_disables_after_recovery_blocks_output(tmp_path):
    _case(tmp_path)
