import logging
import time

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class TimingMiddleware:
    """
    Middleware that records the start time of each request for use in logging or performance monitoring.
    """

    def __init__(self, get_response):
        """
        Store the next middleware or view callable.

        :param get_response: The next component in the middleware chain.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Attach a high-precision start time to the request and log the total elapsed time
        after the response is returned.

        :param request: The incoming HttpRequest object.
        :return: The generated HttpResponse.
        """
        request._start_time = time.perf_counter()
        response = self.get_response(request)
        elapsed = time.perf_counter() - request._start_time
        logger.debug(f"TimingMiddleware: total elapsed time = {elapsed:.3f}s for path {request.path}")
        return response
