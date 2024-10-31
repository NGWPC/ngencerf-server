import logging

from django.dispatch import receiver
from django_dbconn_retry import pre_reconnect, post_reconnect

logger = logging.getLogger(__name__)


@receiver(pre_reconnect)
def pre_reconnect_handler(_sender, _dbwrapper, **_kwargs):
    logger.warning('Attempting to reconnect the  the database...')


@receiver(post_reconnect)
def post_reconnect_handler(_sender, _dbwrapper, **_kwargs):
    logger.warning('Reconnection attempt completed...')
    