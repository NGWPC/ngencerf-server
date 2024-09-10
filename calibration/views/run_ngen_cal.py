import functools
import os
from enum import auto, Enum
from typing import Dict, Optional

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY, get_calibration_input_file, \
    get_calibration_stdout_file, get_validation_control_stdout_file, get_validation_best_input_file, get_validation_control_input_file, \
    get_validation_best_stdout_file
from calibration.views import spawn_process
from calibration.views.common import CerfException
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV


class JobStage(Enum):
    CALIBRATION = auto()
    VALIDATION_CONTROL = auto()
    VALIDATION_BEST = auto()


class JobStageTransitionManager:
    def __init__(self, validation_enabled: bool):
        self.validation_enabled = validation_enabled
        self._initialize_transitions()

    def _initialize_transitions(self):
        self._transitions_no_validation = {
            JobStage.CALIBRATION: None  # End of the state machine
        }

        self._transitions_with_validation = {
            JobStage.CALIBRATION: JobStage.VALIDATION_CONTROL,
            JobStage.VALIDATION_CONTROL: JobStage.VALIDATION_BEST,
            JobStage.VALIDATION_BEST: None  # End of the state machine
        }

    def get_next_stage(self, current_stage: JobStage) -> Optional[JobStage]:
        transitions = (self._transitions_with_validation
                       if self.validation_enabled else self._transitions_no_validation)

        return transitions.get(current_stage)


# Map the cmd values to the corresponding functions
file_funcs = {
    JobStage.CALIBRATION: (get_calibration_input_file, get_calibration_stdout_file),
    JobStage.VALIDATION_CONTROL: (get_validation_control_input_file, get_validation_control_stdout_file),
    JobStage.VALIDATION_BEST: (get_validation_best_input_file, get_validation_best_stdout_file)
}


def run_job(run: CalibrationRun, cmd: JobStage):
    # Retrieve the input and output file functions as a tuple from the dictionary
    file_funcs_tuple = file_funcs.get(cmd)

    if file_funcs_tuple is None:
        raise CerfException(f"Unsupported command: {cmd}")

    # Unpack and call the functions
    input_file_func, output_file_func = file_funcs_tuple
    input_file = input_file_func(run)
    output_file = output_file_func(run)

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

    job_callback = functools.partial(job_stage_callback, stage, do_validation, run)

    spawn_process.execute(run, stage, args, callback_function=job_callback)


def run_docker(run: CalibrationRun, cmd, input_file):
    pass


def job_stage_callback(current_stage: JobStage, do_validation: bool, run: CalibrationRun):
    process_id = os.path.basename(run.job_data_dir)
    print(f'Marking job {process_id}, stage: {current_stage} as done')

    # Create a transition manager for the current job, depending on whether validation is enabled
    transition_manager = JobStageTransitionManager(validation_enabled=do_validation)

    # Determine the next stage
    next_stage = transition_manager.get_next_stage(current_stage)

    if next_stage:
        print(f'Running job {process_id}, stage: {next_stage}')
        run_job(run, next_stage)
    else:
        print(f'Job {process_id} complete. No further stages.')
