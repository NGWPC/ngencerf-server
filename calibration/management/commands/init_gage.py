import csv
from pprint import pprint

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.models import Gage


class Command(BaseCommand):
    help = "Initialize Gage table"

    def handle(self, *args, **options):

        Gage.objects.all().delete()

        # need to get a user that is guaranteed to be there, such as admin
        user = get_user_model().objects.get(username='peter')
        pprint(user)

        with open('calibration/management/commands/USGS_streamflow_gage_list_2024-06-16.txt', 'r') as file:
            reader = csv.reader(file, delimiter='\t')
            row_num = 0
            for row in reader:
                row_num += 1
                print(row_num, row)
                gage = Gage()
                gage.is_active = True
                gage.agency = row[0]
                gage.gage_id = row[1]
                gage.station_name = row[2]
                gage.site_type = row[3]
                gage.latitude = row[4]
                gage.longitude = row[5]
                gage.lat_long_accuracy = row[6]
                gage.lat_long_datum = row[7]
                if len(row) > 9 and row[8]:
                    gage.altitude = row[8]
                if len(row) > 10 and row[9]:
                    gage.altitude_accuracy = row[9]
                if len(row) > 11 and row[10]:
                   gage.altitude_accuracy = row[10]
                if len(row) > 12:
                    gage.huc = row[11]
                if len(row) >= 13 and row[12]:
                    gage.drainage_area = row[12]
                if len(row) >= 14 and row[13]:
                    gage.contrib_drainage_area = row[13]

                gage.updated_by = user
                gage.created_by = user
                gage.save()
