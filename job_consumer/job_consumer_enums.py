from enum import StrEnum


class ConsumerEnvironmentEnum(StrEnum):
    PARALLEL_WORKS = "PARALLEL_WORKS"
    DOCKER = "DOCKER"


class SlurmCallbackStatusEnum(StrEnum):
    SUBMITTED = "SUBMITTED"
    DONE = 'DONE'
    FAILED = 'FAILED'
    CANCELED = 'CANCELED'
    STARTING = 'STARTING'
