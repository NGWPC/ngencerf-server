import logging
from json.decoder import JSONDecodeError

from django.conf import settings
from django.db import transaction
from django.db.models import Func, CharField, F
from django.http import JsonResponse
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.models.status import Status
from calibration.views.common import ResponseException, ResponseValidationError, ResponseJsonError

logger = logging.getLogger(__name__)


class DateToChar(Func):
    arity = 1
    function = 'to_char'
    output_field = CharField()
    template = "%(function)s(%(expressions)s, 'dd-MM-yyyy HH:MI:SS')"


@api_view(['POST'])
# @login_required
def create_calibration_run(request):
    try:
        print('user', request.user)
        logger.debug(f'create_calibration_run() request from {request.user}')

        with transaction.atomic():
            # Need to add request.user to the Run object
            run = CalibrationRun.objects.create(is_active=True, status=Status.objects.get(name=StatusEnum.SAVED.value))

            response = {'message': f'Calibration Run {run.id} created', 'calibration_run_id': run.id}
            logger.debug(f'Returning to {request.user} from create_calibration_run() - {response}')
            return JsonResponse(response, status=status.HTTP_201_CREATED)
    except JSONDecodeError as e:
        return ResponseJsonError(e)
    except serializers.ValidationError as v:
        return ResponseValidationError(v)
    except Exception as e:
        return ResponseException(e)


# noinspection PyUnusedLocal
@api_view(['POST', 'GET'])
# @login_required
def get_jobs(request):
    try:
        logger.debug(f'get_jobs() request from {request.user}')

        # Get all jobs for this user
        # TODO Need to filter jobs by user
        runs = list(CalibrationRun.objects
                    .only('id', 'user_formulation_name', 'gage', 'run_date',
                          'calibration_start_period', 'calibration_end_period', 'status')
                    .annotate(formatted_calibration_start_period=DateToChar('calibration_start_period'),
                              formatted_calibration_end_period=DateToChar('calibration_end_period'))
                    .values('id', 'gage__gage_id', 'run_date', 'formatted_calibration_start_period', 'formatted_calibration_end_period',
                            'status__name', formulation_name=F('user_formulation_name')))
        for r in runs:
            r['calibration_run_id'] = r.pop('id')
            r['gage_id'] = r.pop('gage__gage_id')
            r['status'] = r.pop('status__name')
            r['calibration_start_period'] = r.pop('formatted_calibration_start_period')
            r['calibration_end_period'] = r.pop('formatted_calibration_end_period')

        logger.debug(f'Returning to {request.user} from get_jobs()() - {runs}')
        return JsonResponse(runs, safe=False)
    except JSONDecodeError as e:
        return ResponseJsonError(e)
    except serializers.ValidationError as v:
        return ResponseValidationError(v)
    except Exception as e:
        return ResponseException(e)


# noinspection PyUnusedLocal
@api_view(['POST', 'GET'])
# @login_required
def get_footer(request):
    try:
        response = {"version": settings.VERSION, "contact_email": settings.CONTACT_EMAIL}
        logger.debug(f'Returning to {request.user} from get_footer() - {response}')
        return JsonResponse(response)
    except JSONDecodeError as e:
        return ResponseJsonError(e)
    except serializers.ValidationError as v:
        return ResponseValidationError(v)
    except Exception as e:
        return ResponseException(e)
