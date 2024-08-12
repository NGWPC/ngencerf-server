import json
import logging
from json import JSONDecodeError

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.enums import CalibrationRunType
from calibration.models import CalibrationFormulation
from calibration.util.calibration_validators import ValidationErrorSerializer, ValidationExceptionSerializer, ExceptionResponseSerializer, \
    CalibrationRunValidator, ExportValidator
from calibration.views.calibration_formulation_views import get_my_modules, get_sloth_parameters
from calibration.views.calibration_optimization_views import get_user_optimization
from calibration.views.calibration_tuning_views import get_times, get_parameters_for_export
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @permission_classes([AllowAny])
def export(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'export() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        export_file = {}

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        export_file['gage_id'] = run.gage.gage_id if run.gage else None
        export_file['formulation_name'] = run.user_formulation_name
        export_file['modules'] = get_my_modules(run)
        export_file['use_sloth'] = run.use_sloth
        if run.use_sloth:
            export_file['sloth_parameters'] = get_sloth_parameters(run)
        automatic_validation = run.run_type == CalibrationRunType.VALID_BEST.value
        export_file['automatic_validation'] = automatic_validation
        calibration_times, validation_times = get_times(run, automatic_validation)
        export_file['calibration_times'] = calibration_times
        export_file['validation_times'] = validation_times
        output_variable_to_calibrate = {
            'module': run.module_output_variable.calibration_formulation.name,
            'name': run.module_output_variable.name
        } if run.module_output_variable else None

        export_file['output_variable_to_calibrate'] = output_variable_to_calibrate
        # Get the list of modules for this Run
        modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)
        # For each module, get the Parameters and Output Variables
        parameters = get_parameters_for_export(modules)
        export_file['parameters'] = parameters
        export_file['objective_function'] = run.objective_function.name if run.objective_function else None
        export_file['streamflow_threshold'] = run.streamflow_threshold
        optimization, optimization_inputs = get_user_optimization(run)
        export_file['optimization'] = optimization
        export_file['optimization_inputs'] = optimization_inputs

        # export_file = {key: value for key, value in export_file.items() if value not in [None, '', [], {}]}

        serializer = ExportValidator(data=export_file)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from export() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug(f'Returning to {request.user} from load_formulation_tab() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
