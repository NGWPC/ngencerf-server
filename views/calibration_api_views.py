import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import ReportIterationValidator
from calibration.models import Iteration
from views.common import get_running, JsonException


# Called by ngen_cal
@api_view(['POST'])
# @login_required
def report_iteration(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = ReportIterationValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        iteration_number = validate.data.get('iteration')

        run, errorReturn = get_running(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        with transaction.atomic():
            # TODO Do we always create a new one, or check to see if this iteration number exists?
            # TODO calibration_output_variable_value is required, so add placeholder for now.  Unless it shouldn't be required?
            Iteration.objects.create(calibration_run=run, iteration_num=iteration_number, calibration_output_variable_value=0)
            return JsonResponse({'message': f'Iteration {iteration_number} set for Calibration Run {run.id}', 'calibration_run_id': run.id,
                                 'status': run.status.name},
                                status=status.HTTP_201_CREATED)
    except Exception as e:
        return JsonException(e, traceback.format_exc())
