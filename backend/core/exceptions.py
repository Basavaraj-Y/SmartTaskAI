import logging

from django.db import DatabaseError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, DatabaseError):
        logger.exception("Database request failed", exc_info=exc)
        return Response(
            {
                "detail": "The database is temporarily unavailable. Please try again.",
                "code": "database_unavailable",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return exception_handler(exc, context)
