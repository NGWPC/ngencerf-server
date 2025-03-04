import json
import logging
import os
import time
from typing import Dict

from django.contrib.auth import get_user_model
from django.core.cache import cache
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from swe_mapping.core import run_swe
from swe_timeseries import swe_timeseries

from calibration.enums import StatusEnum, ValidationType
from calibration.models import ValidationRun
from calibration.util.calibration_validators import GetSnodasImagesRequestSerializer, GetSnodasImagesResponseSerializer, \
    ErrorResponseSerializer
from calibration.util.file_util import get_single_file
from calibration.util.ngen_locations import get_geopackage_dir_for_job, get_swe_netcdf_file, get_validation_output_valid, \
    get_output_validation_iteration_plot_dir, get_output_validation_plot_dir, get_output_validation_run_dir
from calibration.views.common import handle_exceptions, validate_request, get_validation_run, png_to_base64_url, get_job_description, \
    validate_response, ResponseError, truncate_large_fields, find_validation_worker_with_matching_log

logger = logging.getLogger(__name__)

User = get_user_model()


def derive_swe_file_inputs(run: ValidationRun) -> Dict[str, str]:
    """
    Derives the common SWE file inputs from the validation run.

    Returns a dict with:
      - 'swe_csv': the path to the SWE CSV file,
      - 'gpkg': the path to the geopackage file.
    """
    validation_type = ValidationType(run.validation_type)
    worker_name = find_validation_worker_with_matching_log(
        run,
        worker_name=run.iteration.worker_name if validation_type == ValidationType.VALID_ITERATION else None,
        iteration_num=run.iteration.iteration_num if validation_type == ValidationType.VALID_ITERATION else None
    )
    swe_csv = get_validation_output_valid(run.calibration_run, worker_name)
    gpkg = get_single_file(get_geopackage_dir_for_job(run.calibration_run))
    return {'swe_csv': swe_csv, 'gpkg': gpkg}


def get_or_create_swe_plots(run: ValidationRun, date: str, plot_dir: str) -> Dict[str, str]:
    """
    Derives file paths based on the validation run, checks the cache,
    and if needed, checks for existing files or calls run_swe.main to generate plots.

    Args:
        run: The validation run object.
        date: The date string (YYYY-MM-DD) for which to generate plots.
        plot_dir: Directory where the plots are stored.

    Returns:
        A dictionary with keys 'sim_map', 'raw_map', and 'lumped_map'
        corresponding to their file paths.
    """
    # Get common SWE file inputs.
    inputs = derive_swe_file_inputs(run)
    swe_csv = inputs['swe_csv']
    gpkg = inputs['gpkg']

    # For swe_map we also need the netCDF.
    swe_netcdf = get_swe_netcdf_file(run.calibration_run)

    # Build paths for the three images.
    sim_map_path = os.path.join(plot_dir, f'sim_map_{date}.png')
    raw_map_path = os.path.join(plot_dir, f'raw_map_{date}.png')
    lumped_map_path = os.path.join(plot_dir, f'lumped_map_{date}.png')

    # Build a cache key based on the run id and date.
    cache_key = f"swe_results_{run.id}_{date}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"Returning cached SWE results for {get_job_description(run)}")
        return cached_result

    # If the files do not exist, run the SWE job.
    if not (os.path.exists(sim_map_path) and os.path.exists(raw_map_path) and os.path.exists(lumped_map_path)):
        swe_args = [
            date,
            swe_csv,
            swe_netcdf,
            gpkg,
            sim_map_path,
            raw_map_path,
            lumped_map_path
        ]
        logger.info(f"Calling run_swe.swe_map with arguments: {swe_args}")
        start_time = time.time()
        run_swe.swe_map(swe_args)
        elapsed_time = time.time() - start_time
        logger.info(f"Finished running run_swe.swe_map in {elapsed_time:.2f} seconds")
    else:
        logger.info(f"SWE files already exist in {plot_dir} for {get_job_description(run)}")

    # Build the result once and cache it.
    result = {
        'sim_map': sim_map_path,
        'raw_map': raw_map_path,
        'lumped_map': lumped_map_path,
    }
    cache.set(cache_key, result)
    return result


def generate_swe_ts_data(validation_run: ValidationRun):
    if validation_run.validation_type != ValidationType.VALID_CONTROL.value:
        # Generate SWE timeseries images.
        inputs = derive_swe_file_inputs(validation_run)
        swe_csv = inputs['swe_csv']
        gpkg = inputs['gpkg']

        # Determine the appropriate plot directory.
        plot_dir = os.path.join(get_plot_dir(validation_run), 'SWE')
        os.makedirs(plot_dir, exist_ok=True)

        swe_args = [
            swe_csv,
            gpkg,
            '--plot_output',
            os.path.join(plot_dir, 'swe_timeseries.png'),
            '--csv_output',
            os.path.join(get_output_validation_run_dir(validation_run.calibration_run),
                         'swe_timeseries_best.csv' if validation_run.validation_type == ValidationType.VALID_BEST.value else f'swe_timeseries_{validation_run.worker_name}_iter{validation_run.iteration_num}')
        ]
        logger.info(f"Calling swe_timeseries.swe_ts with arguments: {swe_args}")
        start_time = time.time()
        swe_timeseries.swe_ts(swe_args)
        elapsed_time = time.time() - start_time
        logger.info(f"Finished running swe_timeseries.swe_ts in {elapsed_time:.2f} seconds")


@extend_schema(
    request=GetSnodasImagesRequestSerializer,
    responses={
        200: GetSnodasImagesResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve a Snodas images for a given date"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_swe_images_by_date(request: Request) -> Response:
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_job_dir() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GetSnodasImagesRequestSerializer, data)
    if error_return:
        return error_return

    validation_run_id = validator.get('validation_run_id')
    date = validator.get('date').strftime("%Y-%m-%d")

    run, error_return = get_validation_run(
        validation_run_id,
        request.user,
        run_status=[StatusEnum.DONE, StatusEnum.RUNNING, StatusEnum.FAILED, StatusEnum.SERVER_ERROR]
    )
    if error_return:
        return error_return

    validation_start_date = run.calibration_run.validation_start_period.strftime("%Y-%m-%d")
    validation_end_date = run.calibration_run.validation_end_period.strftime("%Y-%m-%d")
    if date < validation_start_date or date > validation_end_date:
        return ResponseError(f'Date specified {date} must be within the Validation range {validation_start_date} to {validation_end_date}')

    # Do not allow snodas plots for Validation Control runs.
    if run.validation_type == ValidationType.VALID_CONTROL.value:
        return ResponseError('Snodas plots are not available for a Validation Control run')

    plot_dir = os.path.join(get_plot_dir(run), 'SWE')
    os.makedirs(plot_dir, exist_ok=True)

    # Retrieve or generate the SWE plots using the helper.
    swe_results = get_or_create_swe_plots(run, date, plot_dir)

    generate_swe_ts_data(run)

    response = {
        'message': f'Plots created in {plot_dir}',
        'lumped_map': png_to_base64_url(swe_results['lumped_map']),
        'raw_map': png_to_base64_url(swe_results['raw_map']),
        'sim_map': png_to_base64_url(swe_results['sim_map'])
    }

    response_validator, error_response = validate_response(
        GetSnodasImagesResponseSerializer,
        response,
        fields_to_truncate=['lumped_map', 'raw_map', 'sim_map']
    )
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from get_job_dir() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["lumped_map", "raw_map", "sim_map"]))}'
    )

    return Response(response)


def get_plot_dir(run: ValidationRun) -> str:
    # Determine the appropriate plot directory.
    if run.validation_type == ValidationType.VALID_ITERATION.value:
        plot_dir = os.path.join(get_output_validation_iteration_plot_dir(run.calibration_run, run.iteration_num, run.worker_name))
    else:
        plot_dir = os.path.join(get_output_validation_plot_dir(run.calibration_run))
    return plot_dir
