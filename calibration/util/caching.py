import json

from django.core.cache import cache
from django.db.models import Prefetch

from calibration.enums import PlotDefinitionsEnum
from calibration.enums_vanilla import JobType
from calibration.models import Module, Gage, OptimizationInput, ModuleGroup, CalibrationRun, ValidationRun, ForecastRun


def get_cached_module_by_name(module_name: str) -> Module | None:
    """
    Retrieve a specific module by name from the cache.

    :param module_name: The name of the module.
    :return: The cached module instance if it exists; otherwise None.
    """
    cached_modules: dict[str, Module] = get_cached_modules_with_groups()
    return cached_modules.get(module_name)


CACHED_GAGES_KEY = 'cached_gages'


def get_cached_gages() -> dict[str, dict[str, str | float | int | None]]:
    """
    Retrieves all active gages from the cache or the database if not cached.

    :return: A dictionary of gages with gage_id as the key and gage details as values.
    """
    # Check if the gages are already cached
    gages_lookup = cache.get(CACHED_GAGES_KEY)
    if not gages_lookup:
        # Fetch from the database and cache the results as a dictionary
        gages = Gage.objects.filter(is_active=True).values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude', 'nws_id', 'headwater_calibration', 'domain__name'
        )
        gages_lookup = {gage['gage_id']: gage for gage in gages}
        # Adjust domain names
        for gage in gages_lookup.values():
            gage['domain'] = gage.pop('domain__name')

        cache.set(CACHED_GAGES_KEY, gages_lookup, timeout=None)
    return gages_lookup


def get_gage_by_id(gage_id: str) -> dict[str, str | float | int | None] | None:
    """
    Retrieve a single gage by gage_id from the cached gages.

    :param gage_id: The gage_id to retrieve.
    :return: The gage data if found, otherwise None.
    """
    # Retrieve the gage from the cached set of gages
    gages = get_cached_gages()
    gage = gages.get(gage_id)

    if gage:
        # Exclude 'nws_id', 'domain', and 'headwater_calibration' from the result
        gage = {key: value for key, value in gage.items() if key not in ['nws_id', 'domain', 'headwater_calibration']}

    return gage


def get_cached_optimization_inputs(optimization_name: str) -> list[dict[str, str | int | float]]:
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


def get_cached_modules_with_groups() -> dict[str, Module]:
    """
    Retrieve active Module objects with prefetched groups from cache or database if not cached.

    :return: A dictionary where keys are active module names, and values are Module objects, each with prefetched groups.
    """
    cached_modules: dict[str, Module] = cache.get(MODULE_CACHE_WITH_GROUPS_KEY)

    if cached_modules is None:
        # Prefetch related groups when querying for modules
        modules = Module.objects.filter(is_active=True).prefetch_related(
            Prefetch('groups', queryset=ModuleGroup.objects.only('name'))
        )
        # Cache active modules
        cached_modules = {module.name: module for module in modules}
        cache.set(MODULE_CACHE_WITH_GROUPS_KEY, cached_modules, None)

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


def get_filtered_plot_definitions(
        run: CalibrationRun | ValidationRun | ForecastRun, plot_name: str | None = None, first_match: bool = False
) -> list[dict] | dict | None:
    """
    Retrieve filtered plot definitions for the specified run and plot name, with a case-insensitive match.

    :param run: The run object, which could be a calibration, validation, or forecast run.
    :param plot_name: The name of the plot to filter by (case-insensitive), or None to retrieve all valid plots.
    :param first_match: If True, returns only the first matching plot definition as a dictionary, or None if no match.
    :return: A list of dictionaries representing plot definitions that match the criteria, a single dictionary if first_match is True, or None if no match is found.
    """
    cached_plot_definitions = PlotDefinitionsEnum.get_choices_with_fields(
        fields=['name', 'description', 'valid_optimizations', 'job_type', 'location', 'filename_mask', 'timeseries_available']
    )

    if isinstance(run, ForecastRun):
        # Only return plots for Forecast jobs
        filtered_plots = [
            plot for plot in cached_plot_definitions
            if (plot_name is None or plot['name'].lower() == plot_name.lower())  # Case-insensitive match for plot_name
               and plot['job_type'] == JobType.FORECAST.value  # Ensure it's a forecast plot
        ]

    else:
        # Determine if validation plots should be included
        include_validation_plots = isinstance(run, ValidationRun) or (
                isinstance(run, CalibrationRun) and run.automatic_validation
        )

        optimization = run.optimization if isinstance(run, CalibrationRun) else run.calibration_run.optimization

        # Filter plots based on job type, optimization, and optional plot_name criteria
        filtered_plots = [
            plot for plot in cached_plot_definitions
            if (plot_name is None or plot['name'].lower() == plot_name.lower())  # Case-insensitive match for plot_name
               and plot['valid_optimizations'] is not None  # Exclude plots with null valid_optimizations
               and (optimization.name in json.loads(plot['valid_optimizations']))  # Check valid optimizations
               and (
                       plot['job_type'] == JobType.CALIBRATION.value or
                       (include_validation_plots and plot['job_type'] == JobType.VALIDATION.value)
               )  # Include based on job type
        ]

    # Return the first match if first_match is True, otherwise return the list of matches
    if first_match:
        return filtered_plots[0] if filtered_plots else None
    return filtered_plots
