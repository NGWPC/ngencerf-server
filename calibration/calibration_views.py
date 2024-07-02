import json

from django.db import transaction
from django.db.models import Prefetch
from django.forms import model_to_dict
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from .models import Module, ModuleGroup, Gage, CalibrationRun, StatusEnum, Status


@api_view(['GET', 'POST'])
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


def get_gages(request):
    gages = Gage.objects.filter(is_active=True)
    return JsonResponse(list(gages.values_list('gage_id', flat=True)), safe=False)


@api_view(['POST'])
@transaction.atomic
def save_tab1(request):
    body = json.loads(request.body)
    gage_id = body.get('gage_id')
    forcing_source = body.get('forcing_source')
    forcing_path = body.get('forcing_path')

    gage = Gage.objects.filter(gage_id=gage_id).first()
    if not gage:
        return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

    run = CalibrationRun(gage=gage, forcing_source=forcing_source, forcing_path=forcing_path, is_active=True, status=Status.objects.get(name=StatusEnum.RUNNING.value))
    run.save()
    return JsonResponse({'message': f'Calibration run {run.id} created', 'calibration_run_key': run.id})


@api_view(['GET'])
def test(request):
    Module.objects.all().delete()
    ModuleGroup.objects.all().delete()
    module1 = Module(name='Module1', is_active=True, ngen_cal_active=True)
    module1.save()
    module2 = Module(name='Module2', is_active=True, ngen_cal_active=True)
    module2.save()
    module3 = Module(name='Module3', is_active=True, ngen_cal_active=True)
    module3.save()

    moduleGroup1 = ModuleGroup(name='ModuleGroup1', is_active=True)
    moduleGroup1.save()
    moduleGroup2 = ModuleGroup(name='ModuleGroup2', is_active=True)
    moduleGroup2.save()
    moduleGroup3 = ModuleGroup(name='ModuleGroup3', is_active=True)
    moduleGroup3.save()

    print(model_to_dict(module1))
    module1.groups.add(moduleGroup2)
    module1.save()

    return HttpResponse('hello')
