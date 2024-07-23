import json
import traceback

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator
from calibration.enums import StatusEnum
from calibration.management.commands import ngen_cal_input
from calibration.models import CalibrationRun


@api_view(['GET', 'POST'])
# @login_required()
def is_ready(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        validate = CalibrationRunValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        messages = ngen_cal_input.ready_to_run(run=run)

        response = {'calibration_run_key': run.id, 'status': run.status.name}
        ready_not_ready = 'not ready' if messages else 'ready'
        response['message'] = f'Calibration Run {run.id} is {ready_not_ready}'
        if messages:
            response['errors'] = messages

        return JsonResponse(response)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
