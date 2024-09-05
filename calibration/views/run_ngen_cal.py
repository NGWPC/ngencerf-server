import os

from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, get_stdout_file
from calibration.views import spawn_process
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV


def run_job(run: CalibrationRun, cmd, input_file):
    match settings.RUN_TYPE:
        case settings.RUN_TYPE.LOCAL:
            run_local(run, cmd, input_file)
        case settings.RUN_TYPE.DOCKER:
            raise Exception('Docker not supported')


def run_local(run: CalibrationRun, cmd, input_file):
    cal_or_valid = CALIBRATION_PY if cmd == 'calibration' else 'validation'
    shell_script = os.path.join(settings.BASE_DIR, 'run_ngen_cal', 'run_ngen_cal.sh')

    args = [shell_script, NGEN_CAL_VENV, cal_or_valid, input_file]

    spawn_process.execute(run,  args)


def run_docker(run: CalibrationRun, cmd, input_file):
    pass
