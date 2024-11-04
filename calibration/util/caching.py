import json
from typing import Dict, List, Any

from django.core.cache import cache
from django.db.models import Prefetch

from calibration.enums import PlotDefinitionsEnum
from calibration.models import Module, Gage, Metric, OptimizationInput, ModuleGroup, CalibrationRun


def get_cached_module_by_name(module_name: str) -> Module | None:
    """
    Retrieve a specific module by name from the cache.

    :param module_name: The name of the module.
    :return: The cached module instance if it exists; otherwise None.
    """
    cached_modules: Dict[str, Module] = get_cached_modules_with_groups()
    return cached_modules.get(module_name)


CACHED_GAGES_KEY = 'cached_gages'


def get_cached_gages() -> dict:
    """
    Retrieves all active gages from the cache or the database if not cached.
    :return: A dictionary of gages with gage_id as the key and gage details as values.
    """
    # Check if the gages are already cached
    gages_lookup = cache.get(CACHED_GAGES_KEY)
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


METRICS_LOOKUP_KEY = 'metrics_cache'


def get_metrics_lookup() -> dict:
    """
    Retrieve the Metric objects from cache or database if not cached.

    :return: A dictionary where keys are metric names (lowercased) and values are Metric objects.
    """
    metrics_lookup = cache.get(METRICS_LOOKUP_KEY)
    if not metrics_lookup:
        # Fetch from the database and cache the results
        metrics_lookup = {m.name.lower(): m for m in Metric.objects.all()}
        cache.set('metrics_cache', metrics_lookup, None)  # Cache indefinitely
    return metrics_lookup


METRICS_WITH_FIELDS_KEY = 'active_metrics'


def get_metrics_with_fields():
    """
    Retrieve active metrics with specified fields from cache or database if not cached.

    :return: A list of dictionaries for active metrics, each containing 'name', 'description', 'is_active', 'categorical', and 'event_based' fields.
    """
    metrics = cache.get(METRICS_WITH_FIELDS_KEY)

    # Refresh cache if metrics are not found
    if metrics is None:
        # Fetch metrics from the database if not cached
        metrics = list(Metric.objects.filter(is_active=True).values(
            'name', 'description', 'is_active', 'categorical', 'event_based'
        ))
        cache.set(METRICS_WITH_FIELDS_KEY, metrics, timeout=None)
    return metrics


def get_cached_optimization_inputs(optimization_name: str) -> List[Dict[str, str | int | float]]:
    """
    Retrieve optimization inputs for a specified optimization name from cache or database.

    :param optimization_name: The name of the optimization.
    :return: A list of dictionaries with details of each optimization input (name, description, data_type, etc.).
    """
    cache_key = f'optimization_inputs_{optimization_name}'
    optimization_inputs = cache.get(cache_key)

    # If not in cache, query and cache the results
    if optimization_inputs is None:
        optimization_inputs = list(
            OptimizationInput.objects.filter(optimization__name=optimization_name, is_active=True).values(
                'name', 'description', 'data_type', 'default_value', 'min', 'max', 'id', 'is_active'
            )
        )

        # Cache the inputs
        cache.set(cache_key, optimization_inputs, timeout=None)

    return optimization_inputs


MODULE_CACHE_WITH_GROUPS_KEY = 'module_cache_with_groups'


def get_cached_modules_with_groups() -> Dict[str, Module]:
    """
    Retrieve Module objects with prefetched groups from cache or database if not cached.

    :return: A dictionary where keys are module names, and values are Module objects, each with prefetched groups.
    """
    cached_modules: Dict[str, Module] = cache.get(MODULE_CACHE_WITH_GROUPS_KEY)

    if cached_modules is None:
        # Prefetch related groups when querying for modules
        modules = Module.objects.prefetch_related(
            Prefetch('groups', queryset=ModuleGroup.objects.only('name'))
        )
        # Cache all modules
        cached_modules = {module.name: module for module in modules}
        cache.set(MODULE_CACHE_WITH_GROUPS_KEY, cached_modules, None)  # Cache indefinitely or set a timeout if needed

    return cached_modules


MODULE_GROUPS_CACHE_KEY = 'cached_module_groups'


def get_cached_module_groups() -> list:
    """
    Retrieve a list of active module group names, ordered by 'order', from cache or database if not cached.

    :return: A list of ordered active module group names.
    """
    module_groups = cache.get(MODULE_GROUPS_CACHE_KEY)

    if module_groups is None:
        module_groups = list(ModuleGroup.objects.filter(is_active=True).order_by('order').values_list('name', flat=True))
        cache.set(MODULE_GROUPS_CACHE_KEY, module_groups, None)

    return module_groups

#
# PLOT_CACHE_KEY = 'cached_plot_definitions'
#
#
# def get_filtered_plot_definitions(run, plot_name=None):
#     cached_plot_definitions = cache.get(PLOT_CACHE_KEY)
#
#     # If not cached, query and cache the plot definitions
#     if cached_plot_definitions is None:
#         # Replace PlotDefinitionModel with the actual model name for plot definitions
#         cached_plot_definitions = list(
#             PlotDefinition.objects.filter(is_active=True).values(
#                 'name', 'description', 'valid_optimizations', 'validation', 'location', 'filename_mask'
#             )
#         )
#         cache.set(PLOT_CACHE_KEY, cached_plot_definitions, timeout=None)
#
#     filtered_plot_definitions = []
#
#     for plot in cached_plot_definitions:
#         # Include only plots that match the given plot name, if provided
#         if (plot_name is None or plot['name'] == plot_name) \
#                 and run.optimization.name in json.loads(plot['valid_optimizations']) \
#                 and (run.automatic_validation or not plot['validation']):  # Simplified validation check
#
#             filtered_plot_definitions.append(plot)
#
#     return filtered_plot_definitions


def get_filtered_plot_definition(run: CalibrationRun, plot_name: str | None = None) -> Dict[str, Any] | None:
    """
    Retrieve a single filtered plot definition for the specified run and plot name, with a case-insensitive match.

    :param run: The calibration run instance to check for valid optimizations.
    :param plot_name: The name of the plot to filter by (case-insensitive), or None to consider all plots.
    :return: A dictionary representing the plot definition if found, otherwise None.
    """
    cached_plot_definitions = PlotDefinitionsEnum.active_choices_with_fields(
        fields=['name', 'description', 'valid_optimizations', 'validation', 'location', 'filename_mask']
    )

    for plot in cached_plot_definitions:
        # Perform a case-insensitive comparison for plot_name
        if (plot_name is None or plot['name'].lower() == plot_name.lower()) \
                and run.optimization.name in json.loads(plot['valid_optimizations']) \
                and (run.automatic_validation or not plot['validation']):
            return plot

    return None
