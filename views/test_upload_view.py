import json
import logging
from json.decoder import JSONDecodeError

from django.core.files.storage import FileSystemStorage, default_storage
from django.http import JsonResponse, HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator
from views import ngen_cal_input
from views.common import get_run, JsonException, JsonError, JsonValidationError

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @login_required()
def upload(request):
    print(request.body)
    print('files', request.FILES)
    print('keys', request.FILES.keys())
    for k in request.FILES.keys():
        file = request.FILES[k]
        if default_storage.exists(file.name):
            print('file already exists')
            return HttpResponse('file already exists')
    for k in request.FILES.keys():
        file = request.FILES[k]
        filename = default_storage.save(file.name, file)
        url = default_storage.url(filename)
        print('url', url)
        print('filename', filename)

    return HttpResponse('hello')
