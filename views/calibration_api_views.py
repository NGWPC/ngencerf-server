import json
import traceback

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import ReportIterationValidator
from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Iteration
from calibration.models.status import Status


# Called by ngen_cal
@api_view(['POST'])
# @login_required
def report_iteration(request):
    try:
        print('user', request.user)
        body = json.loads(request.body)
        validate = ReportIterationValidator(data=body or {})
        validate.is_valid(raise_exception=True)

        calibration_run_id = body.get('calibration_run_id')
        iteration_number = body.get('iteration')

        with transaction.atomic():
            # Need to add request.user to the Run object - Will we know the user?  Can Ngen_Cal pass it?
            run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'})
            if run.status != StatusEnum.RUNNING:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not running.  Status: {run.status.name}'})

            # TODO Do we always create a new create, or check to see if this iteration number exists?
            # TODO calibration_output_variable_value is required, so add placeholder for now.  Unless it shouldn't be required?
            iteration = Iteration.objects.create(calibration_run=run, iteration_num=iteration_number, calibration_output_variable_value=0)
            return JsonResponse({'message': f'Iteration {iteration_number} set for Calibration Run {run.id}', 'calibration_run_id': run.id,
                                 'status': run.status.name},
                                status=status.HTTP_201_CREATED)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
