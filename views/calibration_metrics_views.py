import traceback

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.models import Metric


# noinspection PyUnusedLocal
@api_view(['GET', 'POST'])
# @login_required()
def get_metrics(request):
    try:
        metrics = Metric.objects.filter(is_active=True).only('name', 'description', 'categorical').values('name', 'description', 'categorical')
        return JsonResponse(list(metrics), safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
