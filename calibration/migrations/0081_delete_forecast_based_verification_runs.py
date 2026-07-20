from django.db import migrations


def delete_forecast_based_verification_runs(apps, schema_editor):
    VerificationRun = apps.get_model("calibration", "VerificationRun")
    database_alias = schema_editor.connection.alias

    VerificationRun.objects.using(database_alias).filter(
        hindcast_run_id__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("calibration", "0080_calibrationrun_threshold_categorical_and_more"),
    ]

    operations = [
        migrations.RunPython(
            delete_forecast_based_verification_runs,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
