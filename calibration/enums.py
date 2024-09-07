from enum import StrEnum
from typing import List, Dict, Any

from calibration.models import Status, ForcingSource, ObservationalSource
from calibration.util.AbstractEnum import AbstractEnum


class StatusEnum(AbstractEnum):
    SAVED = 'Saved'
    READY = 'Ready'
    RUNNING = 'Running'
    DONE = 'Done'
    FAILED = 'Failed'
    SERVER_ERROR = 'Server error'

    @classmethod
    def get_model(cls):
        return Status


class ForcingSourceEnum(AbstractEnum):
    UPLOAD = 'Upload'

    @classmethod
    def get_model(cls):
        return ForcingSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class ObservationalSourceEnum(AbstractEnum):
    UPLOAD = 'Upload'

    @classmethod
    def get_model(cls):
        return ObservationalSource

    @classmethod
    def get_filter(cls) -> Dict[str, Any]:
        # Apply the filter to only return active statuses
        return {'is_active': True}


class CalibrationRunType(StrEnum):
    CALIB = 'calib'
    VALID_CONTROL = 'valid_control'
    VALID_BEST = 'valid_best'


class DomainEnum(StrEnum):
    ALASKA = 'Alaska'
    HAWAII = 'Hawaii'
    CONUS = 'CONUS'
    PUERTO_RICO = 'Puerto Rico'

    @classmethod
    def values(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class OptimizationEnum(StrEnum):
    DDS = 'DDS'
    GWO = 'GWO'
    PSO = 'PSO'

    @classmethod
    def values(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


####  These enums are used in validators
class DataTypeEnum(StrEnum):
    DOUBLE = 'double'
    INTEGER = 'integer'
    BOOLEAN = 'boolean'
    STRING = 'string'

    @classmethod
    def values(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class LocationEnum(StrEnum):
    NODE = 'node'

    @classmethod
    def values(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]


class UnitsEnum(StrEnum):
    M = 'm'
    NONE = 'none'

    @classmethod
    def values(cls) -> List[str]:
        # noinspection PyUnresolvedReferences
        return [e.value for e in cls]
