import functools
import os
from enum import auto, Enum
from typing import Dict, Optional

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY, get_calibration_input_file, \
    get_calibration_stdout_file, get_validation_stdout_file, get_validation_best_input_file, get_validation_control_input_file
from calibration.views import spawn_process
from calibration.views.common import CerfException
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV


class JobStage(Enum):
    CALIBRATION = auto()
    VALIDATION_CONTROL = auto()
    VALIDATION_BEST = auto()

    # Define the transitions for when validation should be skipped
    _transitions_no_validation: Dict['JobStage', Optional['JobStage']] = {
        CALIBRATION: None  # End of the state machine
    }

    # Define the transitions between stages
    _transitions_with_validation: Dict['JobStage', Optional['JobStage']] = {
        CALIBRATION: VALIDATION_CONTROL,
        VALIDATION_CONTROL: VALIDATION_BEST,
        VALIDATION_BEST: None  # End of the state machine, no further state
    }

    # Method to get the next stage based on whether validation is enabled
    def next_stage(self, validation_enabled: bool = True) -> Optional['JobStage']:
        transitions = (self._transitions_with_validation
                       if validation_enabled else self._transitions_no_validation)
        # noinspection PyUnresolvedReferences
        print('self', self)
        next_stage = transitions.get(self)
        return next_stage


# Map the cmd values to the corresponding functions
input_file_funcs = {
    JobStage.CALIBRATION: get_calibration_input_file,
    JobStage.VALIDATION_BEST: get_validation_best_input_file,
    JobStage.VALIDATION_CONTROL: get_validation_control_input_file,
}


def run_job(run: CalibrationRun, cmd: JobStage):
    input_file = input_file_funcs.get(cmd)(run) if cmd in input_file_funcs else None
    if input_file is None:
        raise CerfException(f"Unsupported command: {cmd}")

    output_file = get_calibration_stdout_file(run) if cmd == JobStage.CALIBRATION else get_validation_stdout_file(run)
    run.status = StatusEnum.from_enum(StatusEnum.RUNNING)
    match settings.RUN_TYPE:
        case settings.RUN_TYPE.LOCAL:
            run_local(run, cmd, input_file, output_file)
        case settings.RUN_TYPE.DOCKER:
            raise Exception('Docker not supported')


def run_local(run: CalibrationRun, stage: JobStage, input_file, output_file):
    cal_or_valid_script = CALIBRATION_PY if stage == JobStage.CALIBRATION else VALIDATION_PY
    shell_script = os.path.join(settings.BASE_DIR, 'run_ngen_cal', 'run_ngen_cal.sh')

    args_to_calibrate_or_validate = [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, cal_or_valid_script] + args_to_calibrate_or_validate

    do_validation = run.automatic_validation

    job_callback = functools.partial(job_stage_callback, stage, do_validation)

    spawn_process.execute(run, stage, args, callback_function=job_callback)


def run_docker(run: CalibrationRun, cmd, input_file):
    pass


def job_stage_callback(current_stage: JobStage, do_validation: bool, run: CalibrationRun):
    """Handles moving to the next stage after completing the current one."""
    print(f'Marking {current_stage} as done')

    # Determine the next stage
    next_stage = current_stage.next_stage(do_validation)

    if next_stage:
        print(f'Running {next_stage}')
        run_job(run, next_stage)
    else:
        print('Job complete. No further stages.')
