import os

from calibration.util.ngen_locations import CALIBRATION_PY
from calibration.views import spawn_process
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV


def run_job(cmd, input_file):
    match settings.RUN_TYPE:
        case settings.RUN_TYPE.LOCAL:
            print('run type', settings.RUN_TYPE)
            run_local(cmd, input_file)
        case settings.RUN_TYPE.DOCKER:
            raise Exception('Docker not supported')


def run_local(cmd, input_file):
    python = os.path.join(NGEN_CAL_VENV, 'bin/python')
    cal_or_valid = CALIBRATION_PY if cmd == 'calibration' else 'validation'
    cmd = [python, cal_or_valid, input_file]
    spawn_process.execute(cmd)


def run_docker(cmd, input_file):
    pass
