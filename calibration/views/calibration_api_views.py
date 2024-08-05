import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authtoken import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.models import Iteration
from calibration.util.calibration_validators import ReportIterationValidator, GenericResponseSerializer
from calibration.views.common import get_running

logger = logging.getLogger(__name__)


@extend_schema(
    request=ReportIterationValidator,
    responses={
        200: GenericResponseSerializer
    },
    description="Report iteration of a running calibration"
)
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
            serializer = GenericResponseSerializer(response)
            logger.debug(f'Returning to {request.user} from report_iteration() - {serializer.data}')

            return Response(serializer.data)
    except JSONDecodeError as e:
            logger.exception(e)
            return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
