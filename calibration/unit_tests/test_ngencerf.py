
import os
from django.contrib.auth.models import User
from django.forms import CharField
from django.test import TestCase
import json

from requests import Response
from calibration.enums import StatusEnum
from calibration.management.commands.init_sql import Command
from calibration.models.gage import Gage
from calibration.models.status import Status
from calibration.views.common import get_run
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory
from calibration.models.plot_definitions import PlotDefinitions
from calibration.views import calibration_import_export_views, calibration_plot_views
from django.db.models.functions import Concat
from django.db.models import Value, CharField
from cerfServer import settings 
from django.core.management import call_command

class CerfUnitTest(TestCase):
    """
    This function initializes the calibration database with a mockup test data in a 
    calibration run record, and returns the run ID for the unit tests' use. It accomplishes
    this by importing Import_test_data/import_complete.json file. 
    """
    def setUp(self):
        user = User.objects.create_user('admin', 'admin@...', 'admin')
        print(f"Username: {user.username}, email: {user.email}")
        # initialize DB static tables (call init_sql and init_gages commands)
        from calibration.management.commands import init_sql
        cmd = init_sql.Command()
        call_command(cmd)
        from calibration.management.commands import init_gages
        cmd = init_gages.Command()
        call_command(cmd)

        factory = APIRequestFactory()
        # Opening import_complete.json file
        f = open(os.path.join(settings.BASE_DIR, 'Import_test_data/import_complete.json'))
        # returns JSON object as a dictionary
        data = json.load(f)
        request = factory.post('/calibration/import/', data, format='json')
        force_authenticate(request, user=user)
        response = calibration_import_export_views.import_job(request)
        response.render()
        res = json.loads(response.content)
        self.run_id = res["calibration_run_id"]
        print(f"Executing setUp(): Calibration run ID = {self.run_id}")
        # verify the record for calibration_run_id
        run, errorReturn = get_run(self.run_id, user)
        if errorReturn:
            return errorReturn
        status=Status.objects.get(name=StatusEnum.RUNNING.value)
        run.status = status
        run.save()

    # Tests the /calibration/get_plot_names/ end-point
    def test_plot_definitions_view(self):
        calibration_run_id = self.run_id
        print(f"Executing test_plot_definitions_view(): Calibration run ID = {self.run_id}")
        factory = APIRequestFactory()
        user = User.objects.get(username='admin')
        if (user == None):
            user = User.objects.create_user('admin', 'test@...', 'tester')
        request = factory.get(f"/calibration/get_plot_names/?calibration_run_id={calibration_run_id}")
        force_authenticate(request, user=user)
        response = calibration_plot_views.get_plot_names(request)
        response.render()
        # check if transaction was successful
        self.assertEqual(response.status_code, 200)

        run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
        if errorReturn:
            return errorReturn
    
        gage_id = run.gage.gage_id
        print(f"test_plot_definitions_view(): Gage ID: {gage_id}")
        plots = (
            PlotDefinitions.objects.filter(is_active=True)
            .annotate(filename=Concat(Value(gage_id), 'filename_mask', output_field=CharField()))
            .values('name', 'description', 'filename')
        )
        expected_response = {f"calibration_run_id": calibration_run_id, "plot_list": list(plots)}
                              
        # verify content
        self.maxDiff = None
        self.assertEqual(json.loads(response.content), expected_response)
        print("Test Passed!!")
