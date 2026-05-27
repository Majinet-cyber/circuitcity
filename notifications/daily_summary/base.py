# notifications/daily_summary/base.py
"""
Abstract interface that every vertical's DailySummaryProvider must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class DailySummaryProvider(ABC):
    """
    Interface for computing and rendering a vertical-aware daily summary.

    Concrete implementations live in retail.py, gym.py, car_hire.py.
    """

    # Human-readable vertical label used in log messages.
    vertical_label: str = "generic"

    @abstractmethod
    def get_metrics(self, business: Any, report_date: date) -> dict[str, Any]:
        """
        Compute and return a plain dict of metrics for ``report_date``.

        The dict is:
          - passed as template context to render_email()
          - stored in NotificationEvent.payload for auditability

        Must NEVER raise; return safe defaults on data errors.
        """

    @abstractmethod
    def render_email(
        self,
        business: Any,
        metrics: dict[str, Any],
        report_date: date,
    ) -> tuple[str, str]:
        """
        Render (html_body, plain_text_body) from the pre-computed metrics dict.
        """
