from enum import StrEnum, auto
from typing import List, Dict, Any, Type

from django.core.cache import cache

from calibration.models import Status, ForcingSource, ObservationalSource, Domain, Optimization, GeopackageSource
from calibration.util.AbstractEnum import AbstractEnum


class StatusEnum(AbstractEnum):
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
    UPLOAD = 'Upload'

    @classmethod
    def get_model(cls) -> Type[ForcingSource]:
        return ForcingSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class ObservationalSourceEnum(AbstractEnum):
    UPLOAD = 'Upload'

    @classmethod
    def get_model(cls) -> Type[ObservationalSource]:
        return ObservationalSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class GeopackageSourceEnum(AbstractEnum):
    UPLOAD = 'Upload'

    @classmethod
    def get_model(cls) -> Type[GeopackageSource]:
        return GeopackageSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class DomainEnum(AbstractEnum):
    @classmethod
    def get_model(cls) -> Type[Domain]:
        return Domain


class OptimizationEnum(AbstractEnum):
    DDS = 'DDS'
    GWO = 'GWO'
    PSO = 'PSO'

    @classmethod
    def get_model(cls) -> Type[Optimization]:
        return Optimization

    @classmethod
    def load_items(cls) -> None:
        model = cls.get_model()
        filter_criteria = cls.get_filter() or {}

        items = model.objects.filter(**filter_criteria).prefetch_related('inputs')

        # Store the results in a dictionary with the item's name as the key
        item_dict = {item.name: item for item in items}

        cache.set(f'{cls.__name__}_cache', item_dict, timeout=None)


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
    VALID_BEST = auto()
    VALID_CONTROL = auto()
    VALID_ITERATION = auto()

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class ValidationMetricPeriod(StrEnum):
    calib = auto()
    valid = auto()
    full = auto()

    @classmethod
    def get_names(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]

#
# class JobStage(StrEnum):
#     """
#     Enum representing the stages of a job.
#     """
#     CALIBRATION = auto()
#     VALIDATION_CONTROL = auto()
#     VALIDATION_BEST = auto()
#
#     @classmethod
#     def get_names(cls) -> List[str]:
#         # noinspection PyUnresolvedReferences
#         return [e.value for e in cls]
#
#     @classmethod
#     def from_string(cls, name: str) -> 'JobStage':
#         """Get an enum object from its string value, case-insensitive."""
#         try:
#             # Look for the enum member using its value, which is case-insensitive here
#             return cls(name.lower())
#         except ValueError:
#             raise ValueError(f"{name} is not a valid {cls.__name__}")
