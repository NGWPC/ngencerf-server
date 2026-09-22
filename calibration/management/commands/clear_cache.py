import logging

from django.core.cache import cache
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Clear Django's configured cache. Safe to run on every startup since sessions are database-backed."


    def handle(self, *args, **options):
        cache.clear()
        logger.info("Django cache cleared.")
