import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from django.http import JsonResponse
from rest_framework import serializers
from rest_framework import status
from rest_framework.authtoken import serializers
from rest_framework.decorators import api_view

from calibration.util.calibration_validators import ReportIterationValidator
from calibration.models import Iteration
from calibration.views.common import get_running, JsonValidationError, JsonException

logger = logging.getLogger(__name__)


# Called by ngen_cal
@api_view(['POST'])
# @login_required
def report_iteration(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'report_iteration() request from {request.user} - {body}')

        validator = ReportIterationValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')
        iteration_number = validator.data.get('iteration')

        run, errorReturn = get_running(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        with transaction.atomic():
            # TODO Do we always create a new one, or check to see if this iteration number exists?
            # TODO calibration_output_variable_value is required, so add placeholder for now.  Unless it shouldn't be required?
            Iteration.objects.create(calibration_run=run, iteration_num=iteration_number, calibration_output_variable_value=0)
            response = {'message': f'Iteration {iteration_number} set for Calibration Run {run.id}', 'calibration_run_id': run.id,
                        'status': run.status.name}
            logger.debug(f'Returning to {request.user} from report_iteration() - {response}')

            return JsonResponse(response, status=status.HTTP_201_CREATED)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)
