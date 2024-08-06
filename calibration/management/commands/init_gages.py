import csv
from pprint import pprint

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import DomainEnum
from calibration.models import Gage, Domain, Rfc

# We have 4 domain specific files to read.  NWMv3_calibration_basins_PR.csv, NWMv3_calibration_basins_HI.csv, NWMv3_calibration_basins_AK.csv, NWMv3_calibration_basins_CONUS.csv
# Note that the column orders are all slightly different
# The gages in these files are marked as NWMv3_calibratable

domains = list(Domain.objects.only('id', 'name').values('id', 'name'))
alaska_domain = next(item for item in domains if item['name'] == DomainEnum.ALASKA.value)
hawaii_domain = next(item for item in domains if item['name'] == DomainEnum.HAWAII.value)
puerto_rico_domain = next(item for item in domains if item['name'] == DomainEnum.PUERTO_RICO.value)
conus_domain = next(item for item in domains if item['name'] == DomainEnum.CONUS.value)


rfc_dict = {rfc['name']: rfc['id'] for rfc in list(Rfc.objects.only('id', 'name').values('id', 'name'))}


class Command(BaseCommand):
    help = "Initialize Gage table"

    def handle(self, *args, **options):
        # Gage.objects.all().delete()

        # need to get a user that is guaranteed to be there, such as admin
        user = get_user_model().objects.get(username='admin')
        pprint(user)

        gages = {}

        with open('calibration/management/commands/NWMv3_calibration_basins_PR.csv') as file:
            # "ID,link_id,longitd,latitud,rfc,snowy,dailyGg,bsnTypN,basnTyp"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                longitude = None if row[2] == 'NA' else float(row[2])
                latitude = None if row[3] == 'NA' else float(row[3])
                rfc_id = rfc_dict[row[4]]
                gage = {'gage_id': row[0], 'longitude': longitude, 'latitude': latitude, 'rfc_id': rfc_id, 'is_active': True, 'nwm_v3_calibrated': True,
                        'domain_id': puerto_rico_domain['id']}
                gages[row[0]] = gage

        with open('calibration/management/commands/NWMv3_calibration_basins_HI.csv') as file:
            # "ID,link_id"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                gage = {'gage_id': row[0], 'is_active': True, 'nwm_v3_calibrated': True, 'domain_id': hawaii_domain['id']}
                gages[row[0]] = gage

        with open('calibration/management/commands/NWMv3_calibration_basins_AK.csv') as file:
            # "ID,link_id,longitd,latitud,snowy,dailyGg,bsnTypN,basnTyp,rfc"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                longitude = None if row[2] == 'NA' else float(row[2])
                latitude = None if row[3] == 'NA' else float(row[3])
                rfc_id = rfc_dict[row[8]]
                gage = {'gage_id': row[0], 'longitude': longitude, 'latitude': latitude, 'rfc_id': rfc_id, 'is_active': True, 'nwm_v3_calibrated': True,
                        'domain_id': alaska_domain['id']}
                gages[row[0]] = gage

        with open('calibration/management/commands/NWMv3_calibration_basins_CONUS.csv') as file:
            # "ID,link_id,rfc,longitd,latitud,snowy,dailyGg,bsnTypN,basnTyp"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                longitude = None if row[3] == 'NA' else float(row[3])
                latitude = None if row[4] == 'NA' else float(row[4])
                rfc_id = rfc_dict[row[2]]
                gage = {'gage_id': row[0], 'longitude': longitude, 'latitude': latitude, 'rfc_id': rfc_id, 'is_active': True, 'nwm_v3_calibrated': True,
                        'domain_id': conus_domain['id']}
                gages[row[0]] = gage

        # Read the main file and supplement with info from the previous file, if available for that gage
        with open('calibration/management/commands/USGS_streamflow_gage_list_2024-06-16.txt', 'r') as file:
            reader = csv.reader(file, delimiter='\t')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first 35 lines
                if row_num <= 35:
                    continue

                gage_id = row[1]
                gage = gages.get(gage_id)
                if not gage:
                    gage = {'gage_id': gage_id, 'is_active': True, 'nwm_v3_calibrated': False}
                    gages[gage_id] = gage

                agency = row[0]

                station_name = row[2]
                site_type = row[3]
                latitude = float(row[4])
                longitude = float(row[5])
                lat_long_accuracy = row[6]
                lat_long_datum = row[7]
                altitude = float(row[8]) if len(row) > 9 and row[8] else None
                altitude_accuracy = row[9] if len(row) > 10 and row[9] else None
                altitude_datum = row[10] if len(row) > 11 and row[10] else None
                huc = row[11] if len(row) > 12 else ''
                drainage_area = float(row[12]) if len(row) >= 13 and row[12] else None
                contrib_drainage_area = float(row[13]) if len(row) >= 14 and row[13] else None

                gage.update({'agency': agency, 'station_name': station_name, 'site_type': site_type,
                             'lat_long_accuracy': lat_long_accuracy, 'lat_long_datum': lat_long_datum,
                             'altitude': altitude, 'altitude_accuracy': altitude_accuracy, 'altitude_datum': altitude_datum, 'huc': huc,
                             'drainage_area': drainage_area, 'contrib_drainage_area': contrib_drainage_area})
                if 'latitude' not in gage or gage['latitude'] is not None:
                    gage.update({'latitude': latitude, 'longitude': longitude})

        # This file maps NWS id with USGS id
        with open('calibration/management/commands/ALL_USGS-HADS_SITES.txt') as file:
            reader = csv.reader(file, delimiter='|')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first 4 lines
                if row_num <= 4:
                    continue

                nws_id = row[0]
                gage_id = row[1].strip()
                gage = gages.get(gage_id)
                if not gage:
                    # print(f"Can't find gage_id '{gage_id}' referenced in ALL_USGS-HADS_SITES.txt, line {row_num}")
                    # According to Yuqiong, there are reservoirs gage and not streamflow gages, so we can ignore them
                    continue
                if 'latitude' not in gage or gage['latitude'] is None:
                    # The ALL_USGS-HADS_SITES.txt file has all longitude values as positive, even though they are in the Western hemisphere.  So we'll switch it.
                    gage['latitude'] = dms_to_dd(row[4].strip())
                    gage['longitude'] = dms_to_dd('-' + row[5].strip())
                    # print('after dms_to_dd', gage['latitude'], gage['longitude'])
                if 'station_name' not in gage or gage['station_name'] is None:
                    gage['station_name'] = row[6]

                gage['nws_id'] = nws_id

        # Additional gages with RFC
        with open('calibration/management/commands/RFC Additional NextGen Calibration Basin List - Sheet1.csv') as file:
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            for row in reader:
                row_num += 1
                # Skip the first lines
                if row_num <= 1:
                    continue

                rfc = row[0]
                rfc_id = rfc_dict[rfc]
                for nws_id in row[1:]:
                    # Find this nws_id in our collection
                    gage = next((item for item in gages.values() if item.get('nws_id') == nws_id), None)
                    if not gage:
                        print(f"Could not find gage with nws_id {nws_id} for rfc {rfc}")
                        continue
                    gage['rfc_id'] = rfc_id

        # Go through all the gages and calculate domain for those that don't have it
        for gage in gages.values():
            if 'domain_id' not in gage or gage['domain_id'] is None:
                # Figure out the domain
                gage['domain_id'] = calculate_domain(gage['latitude'], gage['longitude'])['id']

        # Finally, insert into table
        gage_objects = [Gage(**item) for item in gages.values()]
        Gage.objects.bulk_create(gage_objects, batch_size=1000)


def dms_to_dd(lat_long_str):
    d, m, s = tuple(lat_long_str.split(' '))
    if d[0] == '-':
        dd = float(d) - float(m) / 60 - float(s) / 3600
    else:
        dd = float(d) + float(m) / 60 + float(s) / 3600

    return dd


bounding_boxes = [{'name': 'Alaska', 'upper_right': {'lat': 51.229087747767466, 'long': -179.13657211802118},
                   'lower_left': {'lat': 71.352561, 'long': 179.77488070600702}},
                  {'name': 'Hawaii', 'upper_right': {'lat': 18.91727560534605, 'long': -130.0},
                   'lower_left': {'lat': 22.23238695135951, 'long': -154.80833743387433}},
                  {'name': 'Virgin Islands', 'upper_right': {'lat': 17.679370591195905, 'long': -65.08316619836198},
                   'lower_left': {'lat': 18.38465859717597, 'long': -64.57707574535745}},
                  {'name': 'Puerto Rico', 'upper_right': {'lat': 17.91217576734767, 'long': -67.94024421674217},
                   'lower_left': {'lat': 18.51609472983729, 'long': -65.22314866408664}},
                  ]

# Normalize the longitude, so we don't have to worry about negatives
for b in bounding_boxes:
    b['upper_right']['long'] += 180
    b['lower_left']['long'] += 180


def calculate_domain(lat, long):
    # print(lat, long)
    lat = float(lat)
    long = float(long) + 180.0
    # Oder matters.  Do the unambiguous ones first
    puerto_rico = next(item for item in bounding_boxes if item['name'] == 'Puerto Rico')
    if (puerto_rico['lower_left']['lat'] < lat < puerto_rico['upper_right']['lat']
            and puerto_rico['lower_left']['long'] < lat < puerto_rico['upper_right']['long']):
        return puerto_rico_domain

    virgin_islands = next(item for item in bounding_boxes if item['name'] == 'Virgin Islands')
    if (virgin_islands['lower_left']['lat'] < lat < virgin_islands['upper_right']['lat']
            and virgin_islands['lower_left']['long'] < lat < virgin_islands['upper_right']['long']):
        return puerto_rico_domain

    hawaii = next(item for item in bounding_boxes if item['name'] == 'Hawaii')
    if (hawaii['lower_left']['lat'] < lat < hawaii['upper_right']['lat']
            and hawaii['lower_left']['long'] < lat < hawaii['upper_right']['long']):
        return hawaii_domain

    alaska = next(item for item in bounding_boxes if item['name'] == 'Alaska')
    # For alaska, where just going to check if the lat/long is West of the Eastern border
    if long < alaska['upper_right']['long']:
        return alaska_domain

    # Assume anything else is Conus
    return conus_domain
