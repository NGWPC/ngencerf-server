import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from .calibration_serializers import SaveTab1Serializer
from .models import Module, ModuleGroup, Gage, CalibrationRun, StatusEnum, Status


@api_view(['GET'])
def csrf(request):
    return JsonResponse({'csrf': get_token(request)})


@api_view(['GET', 'POST'])
@login_required()
def get_modules(request):
    modules = Module.objects.filter(is_active=True).prefetch_related(
        Prefetch('groups', queryset=ModuleGroup.objects.only('name').filter(is_active=True)))

    result = []
    for module in modules:
        groups = [group.name for group in module.groups.all()]
        result.append({
            'name': module.name,
            'groups': groups
        })

    return JsonResponse(result, safe=False)


@api_view(['GET', 'POST'])
@login_required()
def get_gage(request, gage_id=None):
    if request.method == 'POST':
        json_body = json.loads(request.body)
        gage_id = json_body.get('gage_id')

    print('gage_id', gage_id)
    if gage_id:
        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

        return JsonResponse(gage, safe=False)
    else:
        return JsonResponse({"error": 'Missing required gage_id'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@login_required()
def get_gages(request):
    gages = Gage.objects.filter(is_active=True)
    return JsonResponse(list(gages.values_list('gage_id', flat=True)), safe=False)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_tab1(request):
    print('user', request.user)
    body = json.loads(request.body)
    ser = SaveTab1Serializer(data=body)
    if not ser.is_valid():
        return JsonResponse({"errors": ser.errors})
    gage_id = body.get('gage_id')
    forcing_source = body.get('forcing_source')
    forcing_path = body.get('forcing_path')

    gage = Gage.objects.filter(gage_id=gage_id).first()
    if not gage:
        return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

    run = CalibrationRun.objects.create(gage=gage, forcing_source=forcing_source, forcing_path=forcing_path, is_active=True,
                                        status=Status.objects.get(name=StatusEnum.RUNNING.value))
    return JsonResponse({'message': f'Calibration run {run.id} created', 'calibration_run_key': run.id})


@api_view(['GET'])
def test_create_tab1(request):
    gage = Gage.objects.filter(gage_id="01010000").first()
    CalibrationRun.objects.create(gage=gage, forcing_source="my_source", forcing_path="my_path", is_active=True,
                                  status=Status.objects.get(name=StatusEnum.RUNNING.value))
    return HttpResponse('ok')


@api_view(['GET'])
def test_update_tab1(request):
    run = CalibrationRun.objects.get(id=13)
    run.forcing_path = 'updated_path'
    run.save()
    return HttpResponse('ok')


@api_view(['GET'])
def test(request):
    return HttpResponse('hello')
