import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calibration", "0081_delete_forecast_based_verification_runs"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="verificationrun",
            name="verif_exactly_one_parent_run",
        ),
        migrations.RemoveIndex(
            model_name="verificationrun",
            name="idx_verif_forecast_run",
        ),
        migrations.RemoveField(
            model_name="calibrationrun",
            name="peak_flow_threshold",
        ),
        migrations.RemoveField(
            model_name="calibrationrun",
            name="streamflow_threshold",
        ),
        migrations.RemoveField(
            model_name="verificationrun",
            name="forecast_run",
        ),
        migrations.AlterField(
            model_name="verificationrun",
            name="hindcast_run",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="verification_runs",
                to="calibration.hindcastrun",
            ),
        ),
    ]