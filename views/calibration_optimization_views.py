import traceback

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.models import Optimization


@api_view(['GET', 'POST'])
# @login_required()
def get_optimizations(request):
    try:
        optimizations = Optimization.objects.filter(is_active=True)
        return JsonResponse(list(optimizations.values('name', 'description')), safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

