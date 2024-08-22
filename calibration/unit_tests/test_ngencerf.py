
from django.contrib.auth.models import User
from django.forms import CharField
from django.test import TestCase
import json

from requests import Response
from calibration.enums import StatusEnum
from calibration.management.commands.init_sql import Command
from calibration.views.common import get_run
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory
from calibration.models.plot_definitions import PlotDefinitions
from calibration.views import calibration_import_export_views, calibration_plot_views
from django.db.models.functions import Concat
from django.db.models import Value, CharField
from cerfServer import settings 

class CerfUnitTest(TestCase):
    """
    This function initializes the calibration database with a mockup test data in a 
    calibration run record, and returns the run ID for the unit tests' use. It accomplishes
    this by importing Import_test_data/import_complete.json file. 
    """
    def setUp(self):
        user = User.objects.get(username='unit_test')
        if (user == None):
            user = User.objects.create_user('unit_test', 'test@...', 'tester')
        print(f"Username: {user.username}")
        #@TODO - initialize static tables in here

        factory = APIRequestFactory()
        # Opening import_complete.json file
        f = open(settings.IMPORT_TEST_DATA_FILE)
        # returns JSON object as a dictionary
        data = json.load(f)
        request = factory.post('/calibration/import/', data, format='json')
        force_authenticate(request, user=user)
        response = calibration_import_export_views.import_job(request)
        response.render()
        res = json.loads(response.content)
        print(f"Response: {response.content}")
        self.run_id = res["run_id"]
        print(f"test_set_up(): Calibration run ID: {self.run_id}")

        return self.run_id

    # Tests the /calibration/get_plot_names/ end-point
    def test_plot_definitions_view(self):
        calibration_run_id = self.run_id
        print(f"test_plot_definitions_view(): Calibration run ID: {self.run_id}")
        factory = APIRequestFactory()
        user = User.objects.get(username='unit_test')
        if (user == None):
            user = User.objects.create_user('unit_test', 'test@...', 'tester')
        request = factory.get(f"/calibration/get_plot_names/?calibration_run_id={calibration_run_id}")
        force_authenticate(request, user=user)
        response = calibration_plot_views.get_plot_names(request)
        response.render()

        run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.SAVED])
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
                              
        # check if transaction was successful
        self.assertEqual(response.status_code, 200)
        # verify content
        self.maxDiff = None
        self.assertEqual(json.loads(response.content), expected_response)
        print("Test Passed!!")
