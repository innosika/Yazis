"""Report generation.

Renders the assignment's report from real evaluation runs: the metric tables and charts
are produced from stored results rather than transcribed, so the document cannot drift
from what the system actually measured.
"""

from __future__ import annotations

from pathlib import Path

from irs.logging import get_logger

log = get_logger("irs.report")


async def generate_report(out_dir: Path) -> int:
    """Write the report and its figures into ``out_dir``.

    Returns:
        A process exit code.
    """
    raise NotImplementedError("report generation is not built yet; run an evaluation first")
