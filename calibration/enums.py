from enum import StrEnum


class StatusEnum(StrEnum):
    SAVED = 'Saved',
    READY = 'Ready',
    RUNNING = 'Running',
    DONE = 'Done',
    CANCELLED = 'Cancelled',
    FAILED = 'Failed',
    RESUMED = 'Resumed',
    SERVER_ERROR = 'Server error'


class CalibrationRunType(StrEnum):
    CALIB = 'calib'
    VALID_CONTROL = 'valid_control'
    VALID_BEST = 'valid_best'


####  These enums are used in validators
class DataTypeEnum(StrEnum):
    DOUBLE = 'double'
    INTEGER = 'integer'
    BOOLEAN = 'boolean'
    STRING = 'string'

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class LocationEnum(StrEnum):
    NODE = 'node'

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class UnitsEnum(StrEnum):
    M = 'm'
    NONE = 'none'

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class ForcingSourceEnum(StrEnum):
    AORC = 'AORC'
    UPLOAD = 'upload'

    @classmethod
    def values(cls):
        return [e.value for e in cls]

class ObservationalSourceEnum(StrEnum):
    USGS = 'USGS'
    USACE = 'USACE'
    BOR = 'BOR'
    ENV = 'ENV'
    CA_DWR = 'CA DWR'
    TX_DOT = 'TX DoT'
    RFC = 'RFC'
    SNOTEL = 'SNOTEL'
    UPLOAD = 'upload'

    @classmethod
    def values(cls):
        return [e.value for e in cls]

