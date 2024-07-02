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
