"""Orchestrating a scan end to end: stage sequencing, post-processing, and
recording what could not be checked.

`run_pipeline` is the whole surface most callers need; the stage functions
behind it are deliberately private to this package.
"""

from .orchestrator import PipelineConfig, PipelineError, run_pipeline

__all__ = ["PipelineConfig", "PipelineError", "run_pipeline"]
