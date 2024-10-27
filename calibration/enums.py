from enum import StrEnum, auto, Enum
from typing import List, Dict, Any, Type

from django.core.cache import cache

from calibration.models import Status, ForcingSource, ObservationalSource, Domain, Optimization, GeopackageSource, PlotDefinition
from calibration.util.AbstractEnum import AbstractEnum


class StatusEnum(AbstractEnum):
    """
    Enum for different statuses with caching support for efficient retrieval.
    """

    SAVED = 'Saved'
    READY = 'Ready'
    RUNNING = 'Running'
    DONE = 'Done'
    CANCELLED = 'Cancelled'
    FAILED = 'Failed'
    SERVER_ERROR = 'Server error'

    @classmethod
    def get_model(cls) -> Type[Status]:
        return Status


class ForcingSourceEnum(AbstractEnum):
    """
    Enum for Forcing Sources, with alias support for 'Upload' or 'User Upload' entries.
    """

    UPLOAD = 'User Upload'

    aliases = {
        UPLOAD: ['Upload', 'User Upload']
    }

    @classmethod
    def get_model(cls) -> Type[ForcingSource]:
        return ForcingSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class ObservationalSourceEnum(AbstractEnum):
    """
    Enum for Observational Sources, with alias support for 'Upload' or 'User Upload' entries.
    """

    UPLOAD = 'User Upload'

    aliases = {
        UPLOAD: ['Upload', 'User Upload']
    }

    @classmethod
    def get_model(cls) -> Type[ObservationalSource]:
        return ObservationalSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class GeopackageSourceEnum(AbstractEnum):
    """
    Enum for Geopackage Sources, with alias support for 'Upload' or 'User Upload' entries.
    """

    UPLOAD = 'User Upload'

    aliases = {
        UPLOAD: ['Upload', 'User Upload']
    }

    @classmethod
    def get_model(cls) -> Type[GeopackageSource]:
        return GeopackageSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class DomainEnum(AbstractEnum):
    """
    Domain Enum with database synchronization.
    """
    @classmethod
    def get_model(cls) -> Type[Domain]:
        return Domain


class OptimizationEnum(AbstractEnum):
    """
    Enum for Optimization types with prefetching for related inputs.
    """

    DDS = 'DDS'
    GWO = 'GWO'
    PSO = 'PSO'

    @classmethod
    def get_model(cls) -> Type[Optimization]:
        return Optimization

    @classmethod
    def load_items(cls) -> None:
        # Fetch optimization items with prefetching for 'inputs' relation
        model = cls.get_model()
        filter_criteria = cls.get_filter() or {}

        items = model.objects.filter(**filter_criteria).prefetch_related('inputs')

        # Store the results in a dictionary with the item's name as the key
        item_dict = {item.name: item for item in items}

        cache.set(f'{cls.__name__}_cache', item_dict, timeout=None)


class PlotDefinitionsEnum(AbstractEnum):
    """
    Enum for Plot Definitions.
    """
    @classmethod
    def get_model(cls) -> Type[PlotDefinition]:
        return PlotDefinition


# Below are standard enums without database synchronization or aliasing.

class DataTypeEnum(StrEnum):
    DOUBLE = 'double'
    INTEGER = 'integer'
    BOOLEAN = 'boolean'
    STRING = 'string'

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class SlurmStatusEnum(StrEnum):
    DONE = 'DONE'
    FAILED = 'FAILED'
    CANCELED = 'CANCELED'

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class LocationEnum(StrEnum):
    NODE = 'node'

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class UnitsEnum(StrEnum):
    M = 'm'
    NONE = 'none'

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class ValidationType(StrEnum):
    VALID_BEST = 'valid_best'
    VALID_CONTROL = 'valid_control'
    VALID_ITERATION = 'valid_iteration'

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


# Used for both ValidationMetrics and NWMRetrospectiveMetrics
class ValidationMetricPeriod(StrEnum):
    calib = auto()
    valid = auto()
    full = auto()

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]
