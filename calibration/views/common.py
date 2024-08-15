import logging

import rest_framework
from rest_framework import status
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.calibration_validators import ErrorResponseSerializer

logger = logging.getLogger(__name__)

#
# # Get an instance of a run by id, but only if owned by the user and either READY or SAVED
# def get_run(calibration_run_id, user):
#     run = CalibrationRun.objects.filter(id=calibration_run_id, owner=user).select_related('status', 'gage').first()
#     if not run:
#         return run, Response({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
#                              status=status.HTTP_400_BAD_REQUEST)
#     if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
#         return run, Response({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
#                              status=status.HTTP_400_BAD_REQUEST)
#     return run, None
#

# This method is only used by report_iteration for now
# Get an instance of a run by id, but only if owned by the user and RUNNING
# def get_running(calibration_run_id, user):
#     run = CalibrationRun.objects.filter(id=calibration_run_id, owner=user).select_related('status', 'gage').first()
#     if not run:
#         return run, Response({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
#                              status=status.HTTP_400_BAD_REQUEST)
#     if run.status.name != StatusEnum.RUNNING:
#         return run, Response({'error': f'Calibration Run {calibration_run_id} is not running.  Status: {run.status.name}'},
#                              status=status.HTTP_400_BAD_REQUEST)
#     return run, None
#


# Get an instance of a run by id, but only if owned by the user and is one of the passed in Statuses
def get_run(calibration_run_id, user, status=None):
    if status is None:
        status = [StatusEnum.READY, StatusEnum.SAVED]
    status_names = [s.name.lower() for s in status]
    run = CalibrationRun.objects.filter(id=calibration_run_id, owner=user).select_related('status', 'gage').first()
    if not run:
        return run, Response({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
                             status=rest_framework.status.HTTP_400_BAD_REQUEST)
    if run.status.name.lower() not in status_names:
        return run, Response({'error': f'Calibration Run {calibration_run_id} is not {join(status_names)}.  Status: {run.status.name}'},
                             status=rest_framework.status.HTTP_400_BAD_REQUEST)
    return run, None


def join(items):
    if not items:
        return ''
    elif len(items) == 1:
        return items[0].lower()
    else:
        return ', '.join(items[:-1]) + ' or ' + items[-1]


def ResponseError(error, httpStatus=status.HTTP_400_BAD_REQUEST):
    response = {'error': error}
    serializer = ErrorResponseSerializer(response)
    logger.error(serializer.data)
    return Response(serializer.data, status=httpStatus)
