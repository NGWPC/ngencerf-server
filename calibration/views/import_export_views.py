import json
import logging

from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)

@api_view(['POST'])
# @permission_classes([AllowAny])
def export(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'report_iteration() request from {request.user} - {body}')

        # validator = ExportValidator(data=body)
        # validator.is_valid(raise_exception=True)

        # calibration_run_id = validator.data.get('calibration_run_id')
        calibration_run_id = 1

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn