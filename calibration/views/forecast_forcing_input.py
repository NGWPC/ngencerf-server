import logging

import yaml
from django.conf import settings
from yaml.nodes import SequenceNode

from calibration.models import ForecastForcingDownloadRun
from calibration.util.ngen_locations import FORCING_MESH_SCRIPT_PATH, FORCING_BMI_SCRIPT_PATH, \
    get_forecast_forcing_cycle_config_file, FORCING_HRRR, get_forecast_forcing_config_file, FORCING_EXTRACTION_SCRIPT_PATH, \
    get_forecast_temp_dir, FORCING_RAW_INPUT, FORCING_ESMF_MESH

logger = logging.getLogger(__name__)


# Custom Dumper to control formatting
class CustomDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless_sequence=False):
        return super(CustomDumper, self).increase_indent(flow, indentless_sequence)


# Formatter for lists to ensure they are rendered in flow style (inline)
def format_list_as_inline(dumper: yaml.Dumper, data: list) -> SequenceNode:
    # Always render lists in inline flow style
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


# Register the custom formatter for lists
CustomDumper.add_representer(list, format_list_as_inline)


def build_forecast_forcing_download_config(run: ForecastForcingDownloadRun):
    wrapper_config_json = {
        'global': {
            'mesh_script_path': FORCING_MESH_SCRIPT_PATH,
            # 'mesh_in_base_path': get_geopackage_dir_for_job(run.forecast_run.calibration_run),
            'mesh_out_base_path': FORCING_ESMF_MESH,
            'extraction_script_path': FORCING_EXTRACTION_SCRIPT_PATH,
            'extraction_out_path': FORCING_RAW_INPUT,
            'bmi_script_path': FORCING_BMI_SCRIPT_PATH,
            'mesh_env': settings.FORCING_MESH_ENV,
            'extract_env': settings.FORCING_EXTRACT_ENV,
            'engine_env': settings.FORCING_ENGINE_ENV
        },
        'short_range': {
            'sr_config_path': get_forecast_forcing_cycle_config_file(run.forecast_run),
            # This will resolve to FORCING_HRRR
            'hrrr_out_path': '/HRRR',
            # This will resolve to FORCING_RAP
            'rap_out_path': '/RAP'
        }
    }

    config_path = get_forecast_forcing_config_file(run.forecast_run)
    with open(config_path, 'w') as yaml_file:
        yaml.dump(wrapper_config_json, yaml_file, Dumper=CustomDumper, default_flow_style=False, sort_keys=False)

    # Build the config for the specific cycle
    function_name = f"build_{run.forecast_run.cycle.internal_name}_config"

    # Retrieve the function from globals and call it
    if function_name in globals():
        globals()[function_name](run)
    else:
        logger.info(f"No function defined with name: {function_name}")


def build_short_range_config(run: ForecastForcingDownloadRun):
    short_range_config_json = {
        'time_step_seconds': 3600,
        'initial_time': 0,
        'NWM_VERSION': 4.0,
        'NWM_CONFIG': "short_range",
        'InputForcings': [5],
        'InputForcingDirectories': [FORCING_HRRR],
        'InputForcingTypes': ["GRIB2"],
        'InputMandatory': [1],
        'OutputFrequency': 60,
        'SubOutputHour': 0,
        'SubOutFreq': 0,
        # TODO Would rather specify a directory in /tmp, but ngen-forcing checks if the directory exists.  Hoping Kyle can change this
        'ScratchDir': get_forecast_temp_dir(run.forecast_run),
        'Output': 1,
        'compressOutput': 0,
        'floatOutput': 0,
        'AnAFlag': 0,
        'LookBack': -9999,
        'RefcstBDateProc': "202311191900",
        'ForecastFrequency': 60,
        'ForecastShift': 0,
        'ForecastInputHorizons': [1080],
        'ForecastInputOffsets': [0],
        'SpatialMetaIn': "",
        'GRID_TYPE': "hydrofabric",
        'NodeCoords': 'nodeCoords',
        'ElemID': 'element_id',
        'ElemCoords': 'centerCoords',
        'ElemConn': 'elementConn',
        'NumElemConn': 'numElementConn',
        'HGTVAR': 'Element_Elevation',
        'SLOPE': 'Element_Slope',
        'SLOPE_AZIMUTH': 'Element_Slope_Azmuith',
        'IgnoredBorderWidths': [0],
        'RegridOpt': [1],
        'ForcingTemporalInterpolation': [0],
        'TemperatureBiasCorrection': [0],
        'PressureBiasCorrection': [0],
        'HumidityBiasCorrection': [0],
        'WindBiasCorrection': [0],
        'SwBiasCorrection': [0],
        'LwBiasCorrection': [0],
        'PrecipBiasCorrection': [0],
        'TemperatureDownscaling': [0],
        'ShortwaveDownscaling': [0],
        'PressureDownscaling': [0],
        'PrecipDownscaling': [0],
        'HumidityDownscaling': [0],
        'DownscalingParamDirs': ["/tmp"],  # Not used, but needs to contain an existing directory
        'SuppPcp': [],
        'SuppPcpForcingTypes': [],
        'SuppPcpDirectories': [],
        'SuppPcpParamDir': '',  # Not used
        'RegridOptSuppPcp': [],
        'SuppPcpTemporalInterpolation': [],
        'SuppPcpInputOffsets': [],
        'SuppPcpMandatory': [],
        'RqiMethod': 0,
        'RqiThreshold': 0.9,
        'cfsEnsNumber': '',
        'custom_input_fcst_freq': [],
        'includeLQFrac': 1
    }

    config_path = get_forecast_forcing_cycle_config_file(run.forecast_run)
    with open(config_path, 'w') as yaml_file:
        yaml.dump(short_range_config_json, yaml_file, Dumper=CustomDumper, default_flow_style=False, sort_keys=False)
