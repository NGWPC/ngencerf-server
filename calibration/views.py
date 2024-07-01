from django.forms import model_to_dict
from django.http import HttpResponse
from rest_framework.decorators import api_view

from .models import Module, ModuleGroup


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
