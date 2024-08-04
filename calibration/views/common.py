import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun

logger = logging.getLogger(__name__)


def get_run(calibration_run_id, user):
    # TODO Need to filter jobs by user
    run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status', 'gage').first()
    if not run:
        return run, JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
                                 status=status.HTTP_400_BAD_REQUEST)
    if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
        return run, JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                 status=status.HTTP_400_BAD_REQUEST)
    return run, None


# This method is only used by report_iteration for now
def get_running(calibration_run_id, user):
    # TODO Need to filter jobs by user
    run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status', 'gage').first()
    if not run:
        return run, JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
                                 status=status.HTTP_400_BAD_REQUEST)
    if run.status.name != StatusEnum.RUNNING:
        return run, JsonResponse({'error': f'Calibration Run {calibration_run_id} is not running.  Status: {run.status.name}'},
                                 status=status.HTTP_400_BAD_REQUEST)
    return run, None


def ResponseError(error, httpStatus=status.HTTP_400_BAD_REQUEST):
    logger.error(error)
    return Response({'error': error}, status=httpStatus)


def ResponseException(e):
    logger.exception(e)
    return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def ResponseValidationError(e):
    logger.exception(e)
    return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def ResponseJsonError(e):
    logger.exception(e)
    return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
