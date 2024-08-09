import csv
import os.path
from pprint import pprint

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import DomainEnum
from calibration.models import Gage, Domain, Rfc

# Gages are loaded from several files
# 1 USGS files
# 2 NWMv3 files.  These are the NWM calibratable gages
# 3 Mapping files to get nws_id
# 4 Additional gages

domains = list(Domain.objects.only('id', 'name').values('id', 'name'))
alaska_domain = next(item for item in domains if item['name'] == DomainEnum.ALASKA.value)
hawaii_domain = next(item for item in domains if item['name'] == DomainEnum.HAWAII.value)
puerto_rico_domain = next(item for item in domains if item['name'] == DomainEnum.PUERTO_RICO.value)
conus_domain = next(item for item in domains if item['name'] == DomainEnum.CONUS.value)

rfc_dict = {rfc['name']: rfc['id'] for rfc in list(Rfc.objects.only('id', 'name').values('id', 'name'))}

gages = {}


class Command(BaseCommand):
    help = "Initialize Gage table"

    def add_arguments(self, parser):
        parser.add_argument('--data_dir', type=str, help='Path to location of gage files')

    def handle(self, *args, **options):
        data_dir = options['data_dir']
        if not data_dir:
            data_dir = 'calibration/management/commands'

        if not os.path.isdir(data_dir) or not os.path.exists(data_dir):
            print(f'{data_dir} must be a directory containing the data files')
            return

        # Gage.objects.all().delete()

        # need to get a user that is guaranteed to be there, such as admin
        user = get_user_model().objects.get(username='admin')
        pprint(user)

        add_usgs_gages(os.path.join(data_dir, 'USGS_gages_CONUS.csv'), conus_domain)
        add_usgs_gages(os.path.join(data_dir, 'USGS_gages_AK.csv'), alaska_domain)
        add_usgs_gages(os.path.join(data_dir, 'USGS_gages_HI.csv'), hawaii_domain)
        add_usgs_gages(os.path.join(data_dir, 'USGS_gages_PR.csv'), puerto_rico_domain)

        with open(os.path.join(data_dir, 'NWMv3_calibration_basins_PR.csv')) as file:
            # "ID,link_id,longitd,latitud,rfc,snowy,dailyGg,bsnTypN,basnTyp"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            new_count = 0
            existing_count = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                gage_count += 1
                gage_id = row[0]
                gage = gages.get(gage_id)
                if not gage:
                    new_count += 1
                    longitude = None if row[2] == 'NA' else float(row[2])
                    latitude = None if row[3] == 'NA' else float(row[3])
                    gage = {'gage_id': gage_id, 'is_active': True, 'nwm_v3_calibrated': True, 'latitude': latitude, 'longitude': longitude,
                            'domain_id': puerto_rico_domain['id']}
                    gages[gage_id] = gage
                else:
                    existing_count += 1
                    # print(f'Gage {gage_id} from NWM PR already exists')

                gage['rfc_id'] = rfc_dict[row[4]]
                gages[gage_id] = gage
        print(f'Processed {gage_count} gages from {file.name}.  {new_count} were new.  {existing_count} existing')

        with open(os.path.join(data_dir, 'NWMv3_calibration_basins_HI.csv')) as file:
            # "ID,link_id"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            new_count = 0
            existing_count = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                gage_count += 1
                gage_id = row[0]
                gage = gages.get(gage_id)
                if not gage:
                    new_count += 1
                    gage = {'gage_id': gage_id, 'is_active': True, 'nwm_v3_calibrated': True,
                            'domain_id': hawaii_domain['id']}
                    gages[gage_id] = gage
                else:
                    existing_count += 1
                    # print(f'Gage {gage_id} from NWM HI already exists')

                gages[gage_id] = gage
        print(f'Processed {gage_count} gages from {file.name}.  {new_count} were new.  {existing_count} existing')

        with open(os.path.join(data_dir, 'NWMv3_calibration_basins_AK.csv')) as file:
            # "ID,link_id,longitd,latitud,snowy,dailyGg,bsnTypN,basnTyp,rfc"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            new_count = 0
            existing_count = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                gage_count += 1
                gage_id = row[0]
                gage = gages.get(gage_id)
                if not gage:
                    new_count += 1
                    longitude = None if row[2] == 'NA' else float(row[2])
                    latitude = None if row[3] == 'NA' else float(row[3])
                    gage = {'gage_id': gage_id, 'is_active': True, 'nwm_v3_calibrated': True, 'latitude': latitude, 'longitude': longitude,
                            'domain_id': alaska_domain['id']}
                    gages[gage_id] = gage
                else:
                    existing_count += 1
                    # print(f'Gage {gage_id}from NWM AK already exists')

                gage['rfc_id'] = rfc_dict[row[8]]
                gages[gage_id] = gage
        print(f'Processed {gage_count} gages from {file.name}.  {new_count} were new.  {existing_count} existing')

        with open(os.path.join(data_dir, 'NWMv3_calibration_basins_CONUS.csv')) as file:
            # "ID,link_id,rfc,longitd,latitud,snowy,dailyGg,bsnTypN,basnTyp"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            new_count = 0
            existing_count = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first line
                if row_num <= 1:
                    continue

                gage_count += 1
                gage_id = row[0]
                gage = gages.get(gage_id)
                if not gage:
                    new_count += 1
                    longitude = None if row[3] == 'NA' else float(row[3])
                    latitude = None if row[4] == 'NA' else float(row[4])
                    gage = {'gage_id': gage_id, 'is_active': True, 'nwm_v3_calibrated': True, 'latitude': latitude, 'longitude': longitude,
                            'domain_id': conus_domain['id']}
                    gages[gage_id] = gage
                else:
                    existing_count += 1
                    # print(f'Gage {gage_id} from NWM CONUS already exists')

                gage['rfc_id'] = rfc_dict[row[2]]
                gages[row[0]] = gage
        print(f'Processed {gage_count} gages from {file.name}.  {new_count} were new.  {existing_count} existing')

        # Some extra manually added gages
        with open(os.path.join(data_dir, 'Supplemental - AK.csv')) as file:
            # "gage_id,nws_id,lat,long"
            reader = csv.reader(file, delimiter=',')
            row_num = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first 3 lines
                if row_num <= 3:
                    continue

                gage_count += 1
                gage = {'gage_id': row[0], 'nws_id': row[1], 'longitude': row[3], 'latitude': row[2], 'station_name': row[4], 'is_active': True,
                        'nwm_v3_calibrated': False, 'domain_id': alaska_domain['id']}
                gages[row[0]] = gage
        print(f'Processed {gage_count} gages from {file.name}.')

        # This file maps NWS id with USGS id
        with open(os.path.join(data_dir, 'ALL_USGS-HADS_SITES.txt')) as file:
            reader = csv.reader(file, delimiter='|')
            row_num = 0
            gage_count = 0
            for row in reader:
                row_num += 1
                # Skip the first 4 lines
                if row_num <= 4:
                    continue

                nws_id = row[0].strip()
                gage_id = row[1].strip()
                gage = gages.get(gage_id)
                if not gage:
                    # print(f"Can't find gage_id '{gage_id}' referenced in ALL_USGS-HADS_SITES.txt, line {row_num}")
                    # According to Yuqiong, there are reservoir gage and not streamflow gages, so we can ignore them
                    continue
                gage_count += 1

                if 'latitude' not in gage or gage['latitude'] is None:
                    print(f'Adding lat/long for gage {gage_id}')
                    # The ALL_USGS-HADS_SITES.txt file has all longitude values as positive, even though they are in the Western hemisphere.  So we'll switch it.
                    gage['latitude'] = dms_to_dd(row[4].strip())
                    gage['longitude'] = dms_to_dd('-' + row[5].strip())
                if 'station_name' not in gage or gage['station_name'] is None:
                    gage['station_name'] = row[6]

                gage['nws_id'] = nws_id
        print(f'Processed {gage_count} gages from {file.name}.')

        add_additional_gages(os.path.join(data_dir, 'RFC Additional NextGen Calibration Basin List - AK.csv'), alaska_domain)
        add_additional_gages(os.path.join(data_dir, 'RFC Additional NextGen Calibration Basin List - CONUS.csv'), conus_domain)

        unique_field = 'gage_id'
        print()
        print('Creating objects.... this will take a minute or two')
        row_num = 0
        for gage in gages.values():
            Gage.objects.update_or_create(defaults={key: value for key, value in gage.items() if key != unique_field},
                                          **{unique_field: gage[unique_field]})
            row_num += 1
            if row_num % 1000 == 0:
                print(row_num, 'of', len(gages), '...')


def add_additional_gages(gage_file, domain):
    with open(gage_file) as file:
        reader = csv.reader(file, delimiter=',')
        row_num = 0
        gage_count = 0
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
                gage_count += 1
                gage['rfc_id'] = rfc_id
                gage['domain_id'] = domain['id']
    print(f'Processed {gage_count} gages from {file.name}.')


def add_usgs_gages(usgs_file, domain):
    # Read the main file and supplement with info from the previous file, if available for that gage
    with open(usgs_file, 'r') as file:
        reader = csv.reader(file, delimiter='\t')
        row_num = 0
        gage_count = 0
        for row in reader:
            row_num += 1
            # Skip the first 34 lines
            if row_num <= 34:
                continue

            gage_count += 1
            gage_id = row[1]
            # There shouldn't be any overlap in the USGS files, so we should always be creating a new entry.
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

            gage.update({'agency': agency, 'station_name': station_name, 'site_type': site_type,
                         'lat_long_accuracy': lat_long_accuracy, 'lat_long_datum': lat_long_datum,
                         'altitude': altitude, 'altitude_accuracy': altitude_accuracy, 'altitude_datum': altitude_datum, 'huc': huc,
                         'drainage_area': drainage_area, 'latitude': latitude, 'longitude': longitude, 'domain_id': domain['id']})

    print(f'Processed {gage_count} gages from {file.name}.')


def dms_to_dd(lat_long_str):
    d, m, s = tuple(lat_long_str.split(' '))
    if d[0] == '-':
        dd = float(d) - float(m) / 60 - float(s) / 3600
    else:
        dd = float(d) + float(m) / 60 + float(s) / 3600

    return dd


bounding_boxes = [{'name': 'Alaska', 'upper_right': {'lat': 51.229087747767466, 'long': -157.68842},
                   'lower_left': {'lat': 71.352561, 'long': -139.55319}},
                  {'name': 'Hawaii', 'upper_right': {'lat': 18.91727560534605, 'long': -160.33116},
                   'lower_left': {'lat': 22.23238695135951, 'long': -154.80833743387433}},
                  {'name': 'Puerto Rico', 'upper_right': {'lat': 17.91217576734767, 'long': -67.33337},
                   'lower_left': {'lat': 18.51609472983729, 'long': -64.48663}},
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
