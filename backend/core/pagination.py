"""Пагинация API.

Размер страницы задаётся запросом: табличный режим забирает всю школу
одним куском, дашборды и списки — по умолчанию. Без `page_size_query_param`
DRF молча отдаёт первые 50 записей, и директор не видит остальных учеников,
причём ничто в интерфейсе на это не намекает.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Страница по умолчанию 50, по запросу — до 500."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
