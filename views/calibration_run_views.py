import json
import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator
from calibration.management.commands import ngen_cal_input
from views.common import get_run, JsonException

logger = logging.getLogger(__name__)


@api_view(['GET', 'POST'])
# @login_required()
def is_ready(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        validate = CalibrationRunValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        messages = ngen_cal_input.ready_to_run(run=run)

        response = {'calibration_run_key': run.id, 'status': run.status.name}
        ready_not_ready = 'not ready' if messages else 'ready'
        response['message'] = f'Calibration Run {run.id} is {ready_not_ready}'
        if messages:
            response['errors'] = messages

        return JsonResponse(response)
    except Exception as e:
        return JsonException(e)
