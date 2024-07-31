import collections
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
        user = get_user_model().objects.get(username='admin')
        pprint(user)

        gage_dict = collections.defaultdict(dict)

        # This file maps NWS id with USGS id
        with open('calibration/management/commands/ALL_USGS-HADS_SITES.txt') as file:
            reader = csv.reader(file, delimiter='|')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first 4 lines
                if row_num < 5:
                    continue

                subdict = gage_dict[row[1]]
                subdict['nws'] = row[0]

        # This file has all the calibratable gages.  By virtue of being in this file, the gage will be marked as calibratable
        # We'll also save the RFC field
        with open('calibration/management/commands/NWMv3_calibration_list.csv') as file:
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            # Save the RFC and indicate that this gage is calibratable
            for row in reader:
                row_num += 1
                # Skip the first 1 lines
                if row_num < 2:
                    continue

                subdict = gage_dict[row[0]]
                subdict['calibratable'] = True
                subdict['rfc'] = row[2]

            print(gage_dict)

        # Read the main file and supplement with info from the previous file, if available for that gage
        with open('calibration/management/commands/USGS_streamflow_gage_list_2024-06-16.txt', 'r') as file:
            reader = csv.reader(file, delimiter='\t')
            row_num = 0
            for row in reader:
                row_num += 1

                is_active = True
                agency = row[0]
                gage_id = row[1]
                station_name = row[2]
                site_type = row[3]
                latitude = row[4]
                longitude = row[5]
                lat_long_accuracy = row[6]
                lat_long_datum = row[7]
                altitude = row[8] if len(row) > 9 and row[8] else None
                altitude_accuracy = row[9] if len(row) > 10 and row[9] else None
                altitude_datum = row[10] if len(row) > 11 and row[10] else None
                huc = row[11] if len(row) > 12 else ''
                drainage_area = row[12] if len(row) >= 13 and row[12] else None
                contrib_drainage_area = row[13] if len(row) >= 14 and row[13] else None

                subdict = gage_dict[gage_id]
                print(row_num, row, subdict)

                rfc = None
                nws_id = None
                calibratable = False
                if subdict:
                    calibratable = subdict.get('calibratable', False)
                    rfc = subdict.get('rfc')
                    nws_id = subdict.get('nws')

                Gage.objects.get_or_create(gage_id=gage_id, defaults={
                    'is_active': is_active, 'agency': agency, 'station_name': station_name, 'site_type': site_type,
                    'latitude': latitude, 'longitude': longitude, 'lat_long_accuracy': lat_long_accuracy, 'lat_long_datum': lat_long_datum,
                    'altitude': altitude, 'altitude_accuracy': altitude_accuracy,
                    'altitude_datum': altitude_datum,
                    'huc': huc, 'drainage_area': drainage_area, 'contrib_drainage_area': contrib_drainage_area, 'calibratable': calibratable,
                    'rfc': rfc, 'nws_id': nws_id, 'updated_by': user, 'created_by': user
                })
