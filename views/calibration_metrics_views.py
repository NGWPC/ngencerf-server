import json
import traceback

from django.db import transaction
from django.forms import model_to_dict
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import MetricNameValidator
from calibration.models import Metric, MetricInput


# noinspection PyUnusedLocal
@api_view(['GET', 'POST'])
# @login_required()
def get_metrics(request):
    try:
        metrics = Metric.objects.filter(is_active=True)
        return JsonResponse(list(metrics.values('name', 'description')), safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# noinspection PyUnusedLocal
@api_view(['GET', 'POST'])
# @login_required()
def get_metric_inputs(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = MetricNameValidator(data=body)
        validate.is_valid(raise_exception=True)

        metric_name = validate.data.get('metric')

        if not Metric.objects.filter(name=metric_name).exists():
            return JsonResponse({'message': f'Metric {metric_name} does not exist'})
        inputs = MetricInput.objects.filter(metric__name=metric_name).all().values("name", "description", "default_value", "data_type")
        print('inputs', list(inputs))

        return JsonResponse(list(inputs), safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
