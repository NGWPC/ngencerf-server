import json
import logging
import os
import time

from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from swe_mapping.core import run_swe

from calibration.enums import StatusEnum, ValidationType
from calibration.util.calibration_validators import GetSnodasImagesRequestSerializer, GetSnodasImagesResponseSerializer, \
    ErrorResponseSerializer
from calibration.util.file_util import get_single_file
from calibration.util.ngen_locations import get_geopackage_dir_for_job, get_swe_netcdf_file, get_validation_output_valid, \
    get_output_validation_iteration_plot_dir, get_output_validation_plot_dir
from calibration.views.common import handle_exceptions, validate_request, get_validation_run, png_to_base64_url, get_job_description, \
    validate_response, ResponseError, truncate_large_fields
from calibration.views.end_of_job_processing import find_validation_worker_with_matching_log

logger = logging.getLogger(__name__)

User = get_user_model()


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
def get_snodas_images(request: Request) -> Response:
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_job_dir() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GetSnodasImagesRequestSerializer, data)
    if error_return:
        return error_return

    validation_run_id = validator.get('validation_run_id')
    date = validator.get('date').strftime("%Y-%m-%d")

    run, error_return = get_validation_run(validation_run_id, request.user,
                                           run_status=[StatusEnum.DONE, StatusEnum.RUNNING, StatusEnum.FAILED, StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    validation_start_date = run.calibration_run.validation_start_period.strftime("%Y-%m-%d")
    validation_end_date = run.calibration_run.validation_end_period.strftime("%Y-%m-%d")
    if date < validation_start_date or date > validation_end_date:
        return ResponseError(f'Date specified {date} must be within the Validation range {validation_start_date} to {validation_end_date}')

    # Convert validation_type to an instance of ValidationType
    validation_type = ValidationType(run.validation_type)
    if validation_type == ValidationType.VALID_CONTROL:
        return ResponseError('Snodas plots are not avialable for a Validation Control run')

    # Get the worker for the Valid_Best run
    worker_name = find_validation_worker_with_matching_log(
        run,
        worker_name=run.iteration.worker_name if validation_type == ValidationType.VALID_ITERATION else None,
        iteration_num=run.iteration.iteration_num if validation_type == ValidationType.VALID_ITERATION else None
    )
    swe_csv = get_validation_output_valid(run.calibration_run, worker_name)
    # file to be created
    swe_netcdf = get_swe_netcdf_file(run.calibration_run)
    gpkg = get_single_file(get_geopackage_dir_for_job(run.calibration_run))
    plot_dir = os.path.join((get_output_validation_iteration_plot_dir(run.calibration_run, run.iteration_num, run.worker_name)
                             if run.validation_type == ValidationType.VALID_ITERATION.value
                             else get_output_validation_plot_dir(run.calibration_run)), 'SWE')
    os.makedirs(plot_dir, exist_ok=True)

    sim_map_path = os.path.join(plot_dir, f'sim_map_{date}.png')
    raw_map_path = os.path.join(plot_dir, f'raw_map_{date}.png')
    lumped_map_path = os.path.join(plot_dir, f'lumped_map_{date}.png')
    if os.path.exists(sim_map_path) and os.path.exists(raw_map_path) and os.path.exists(lumped_map_path):
        logger.info(f'SWE files for {get_job_description(run)} already exist in {plot_dir}')
    else:
        swe_args = [date, swe_csv, swe_netcdf, gpkg,
                    sim_map_path,
                    raw_map_path,
                    lumped_map_path
                    ]
        logger.info(f"Calling run_swe.main with {swe_args}")
        start_time = time.time()
        run_swe.main(swe_args)
        elapsed_time = time.time() - start_time
        logger.info(f"Finished running run_swe in {elapsed_time:.2f} seconds")

    response = {
        'message': f'Plots created in {plot_dir}',
        'lumped_map': png_to_base64_url(lumped_map_path),
        'raw_map': png_to_base64_url(raw_map_path),
        'sim_map': png_to_base64_url(sim_map_path)
    }

    response_validator, error_response = validate_response(GetSnodasImagesResponseSerializer, response,
                                                           fields_to_truncate=['lumped_map', 'raw_map', 'sim_map'])
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from get_job_dir() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["lumped_map", "raw_map", "sim_map"]))}'
    )

    return Response(response)
