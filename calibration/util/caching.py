from typing import Dict

from django.core.cache import cache

from calibration.models import Module, Gage
from calibration.views.common import get_cached_modules_with_groups


def get_cached_module_by_name(module_name: str) -> Module | None:
    """
    Retrieve a specific module by name from the cache.

    :param module_name: The name of the module.
    :return: The cached module instance if it exists; otherwise None.
    """
    cached_modules: Dict[str, Module] = get_cached_modules_with_groups()
    return cached_modules.get(module_name)


def get_cached_gages() -> dict:
    """
    Retrieves all active gages from the cache or the database if not cached.
    :return: A dictionary of gages with gage_id as the key and gage details as values.
    """
    # Check if the gages are already cached
    gages_lookup = cache.get('cached_gages')
    if not gages_lookup:
        # Fetch from the database and cache the results as a dictionary
        gages = Gage.objects.filter(is_active=True).values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude', 'nws_id', 'nwm_v3_calibrated', 'domain__name'
        )
        gages_lookup = {gage['gage_id']: gage for gage in gages}
        # Adjust domain names
        for gage in gages_lookup.values():
            gage['domain'] = gage.pop('domain__name')

        cache.set('cached_gages', gages_lookup, timeout=None)
    return gages_lookup


def get_gage_by_id(gage_id: str):
    """
    Retrieve a single gage by gage_id from the cached gages.
    :param gage_id: The gage_id to retrieve.
    :return: The gage data if found, otherwise None.
    """
    # Retrieve the gage from the cached set of gages
    gages = get_cached_gages()
    gage = gages.get(gage_id)

    if gage:
        # Exclude 'nws_id', 'domain', and 'nwm_v3_calibrated' from the result
        gage = {key: value for key, value in gage.items() if key not in ['nws_id', 'domain', 'nwm_v3_calibrated']}

    return gage
