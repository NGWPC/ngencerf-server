import functools
import os
from enum import StrEnum, auto

from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY, get_calibration_input_file, get_validation_input_file, \
    get_calibration_stdout_file, get_validation_stdout_file
from calibration.views import spawn_process
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV


class CalibOrValid(StrEnum):
    CALIBRATION = auto()
    VALIDATION = auto()


def run_job(run: CalibrationRun, cmd: CalibOrValid):
    input_file = get_calibration_input_file(run) if cmd == CalibOrValid.CALIBRATION else get_validation_input_file(run)
    output_file = get_calibration_stdout_file(run) if cmd == CalibOrValid.CALIBRATION else get_validation_stdout_file(run)
    match settings.RUN_TYPE:
        case settings.RUN_TYPE.LOCAL:
            run_local(run, cmd, input_file, output_file)
        case settings.RUN_TYPE.DOCKER:
            raise Exception('Docker not supported')


def run_local(run: CalibrationRun, cmd: CalibOrValid, input_file, output_file):
    cal_or_valid_script = CALIBRATION_PY if cmd == CalibOrValid.CALIBRATION else VALIDATION_PY
    shell_script = os.path.join(settings.BASE_DIR, 'run_ngen_cal', 'run_ngen_cal.sh')

    args_to_calibrate_or_validate = [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, cal_or_valid_script] + args_to_calibrate_or_validate

    do_validation = run.automatic_validation and cmd == CalibOrValid.CALIBRATION
    validation_callback = functools.partial(validation_callback_function, do_validation)

    spawn_process.execute(run, args, validation_callback=validation_callback)


def run_docker(run: CalibrationRun, cmd, input_file):
    pass


def validation_callback_function(do_validation, run: CalibrationRun):
    if do_validation:
        print(f"Automatic validation triggered for run {run.id}")
        run_job(run, CalibOrValid.VALIDATION)
