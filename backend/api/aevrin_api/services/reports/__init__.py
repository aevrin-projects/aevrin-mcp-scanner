"""Report rendering, kept out of the router so the route stays a thin HTTP layer."""

from .html import render_report_html

__all__ = ["render_report_html"]
