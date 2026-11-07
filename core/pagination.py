from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):  # type: ignore[misc]
    """The one pagination class of the API: ``count``, ``next``, ``previous``, ``results``.

    ``?page=`` picks the page and ``?page_size=`` changes its size up to ``max_page_size``.
    The three polling lists (nearby restaurants, messages after a sequence number, staff
    orders since a time) keep their own shapes and do not use it.
    """

    page_size_query_param = "page_size"
    max_page_size = 100
