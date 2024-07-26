from django.http import JsonResponse
from rest_framework import status

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun


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


def JsonError(error, httpStatus=status.HTTP_400_BAD_REQUEST):
    print(error)
    return JsonResponse({'error': error}, status=httpStatus, safe=False)


def JsonException(e, stacktrace):
    print(stacktrace)
    return JsonResponse({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
