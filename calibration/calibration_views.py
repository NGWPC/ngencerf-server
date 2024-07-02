import json
from pprint import pprint

from django.forms import model_to_dict
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view

from .models import Module, ModuleGroup, Gage
from rest_framework import status


@api_view(['GET'])
def get_modules(request):
    modules = Module.objects.filter(is_active=True)
    print(list(modules.values_list('name', 'groups__name')))
    return JsonResponse(list(modules.values_list('name', 'groups')))


@api_view(['GET', 'POST'])
def get_gages(request, gage_id=None):
    print('gage_id', gage_id)
    print('requests', request.GET)
    # print('body', request.body)
    # print('json', json.loads(request.body))
    if gage_id:
        gage = Gage.objects.filter(gage_id=gage_id).only("agency", "station_name").first()
        if not gage:
            return HttpResponse(f'Gage {gage_id} does not exist', status=status.HTTP_404_NOT_FOUND)
        print('gage', gage)
        return JsonResponse(gage, safe=False)
    else:
        gages = Gage.objects.filter(is_active=True)
        print(list(gages.values_list('gage_id', flat=True)))
        return JsonResponse(list(gages.values_list('gage_id', flat=True)), safe=False)


@api_view(['GET'])
def test(request):
    Module.objects.all().delete()
    ModuleGroup.objects.all().delete()
    module1 = Module(name="Module1", is_active=True, ngen_cal_active=True)
    module1.save()
    module2 = Module(name="Module2", is_active=True, ngen_cal_active=True)
    module2.save()
    module3 = Module(name="Module3", is_active=True, ngen_cal_active=True)
    module3.save()

    moduleGroup1 = ModuleGroup(name="ModuleGroup1", is_active=True)
    moduleGroup1.save()
    moduleGroup2 = ModuleGroup(name="ModuleGroup2", is_active=True)
    moduleGroup2.save()
    moduleGroup3 = ModuleGroup(name="ModuleGroup3", is_active=True)
    moduleGroup3.save()

    print(model_to_dict(module1))
    module1.groups.add(moduleGroup2)
    module1.save()

    return HttpResponse("hello")
