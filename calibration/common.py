from calibration.models import CalibrationRun, Status, StatusEnum


def get_or_create_calibration_run(calibration_run_id):
    if calibration_run_id:
        return CalibrationRun.objects.filter(id=calibration_run_id).first()
    else:
        return CalibrationRun.objects.create(is_active=True, status=Status.objects.get(name=StatusEnum.RUNNING.value))
