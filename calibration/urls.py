from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from calibration.views import calibration_formulation_views, calibration_tuning_views, calibration_gage_views, \
    calibration_optimization_views, calibration_run_views, calibration_plot_views, calibration_import_export_views, calibration_landing_views, \
    calibration_evaluation_views

urlpatterns = [
    ##################################
    # Landing page
    ##################################
    path('calibration/create_calibration_run/', calibration_landing_views.create_calibration_run, name="createCalibrationRun"),
    path('calibration/create_and_run_validation/', calibration_landing_views.create_and_run_validation, name="createValidationRun"),
    path('calibration/get_footer/', calibration_landing_views.get_footer, name="getFooter"),
    path('calibration/get_calibration_jobs/', calibration_landing_views.get_calibration_jobs, name="getCalibrationJobs"),
    path('calibration/get_calibration_jobs_for_evaluation/', calibration_landing_views.get_calibration_jobs_for_evaluation,
         name="getCalibrationJobsForEvaluation"),
    path('calibration/get_calibration_jobs_for_forecast/', calibration_landing_views.get_calibration_jobs_for_forecast,
         name="getCalibrationJobsForForecast"),
    path('calibration/get_validation_jobs/', calibration_evaluation_views.get_validation_jobs, name="getValidationJobs"),
    path('calibration/load_calibration_run/', calibration_landing_views.load_calibration_run, name="loadCalibrationRun"),
    path('calibration/delete_job/', calibration_landing_views.delete_job, name="deleteJob"),
    path('calibration/clone_job/', calibration_landing_views.clone_job, name="cloneJob"),

    ##################################
    # Gage tab
    ##################################
    path('calibration/get_gage/', calibration_gage_views.get_gage, name="getGage"),
    path('calibration/load_gage_tab/', calibration_gage_views.load_gage_tab, name="loadGageTab"),
    path('calibration/upload_observational_data/', calibration_gage_views.upload_observational_data, name="uploadObservationalData"),
    path('calibration/upload_forcing_data/', calibration_gage_views.upload_forcing_data, name="uploadForcingData"),
    path('calibration/upload_geopackage_data/', calibration_gage_views.upload_geopackage_data, name="uploadGeopackageData"),
    path('calibration/save_gage_tab/', calibration_gage_views.save_gage_tab, name="saveGageTab"),

    ##################################
    # Plot Definitions tab
    ##################################
    path('calibration/get_plot_names/', calibration_plot_views.get_plot_names, name="getPlotNames"),
    path('calibration/get_plot/', calibration_plot_views.get_plot, name="getPlot"),

    ##################################
    # Formulation tab
    ##################################
    path('calibration/load_formulation_tab/', calibration_formulation_views.load_formulation_tab, name="loadFormulationTab"),
    path('calibration/save_formulation_tab/', calibration_formulation_views.save_formulation_tab, name="saveFormulationTab"),

    ##################################
    # Tuning tab
    ##################################
    path('calibration/load_tuning_tab/', calibration_tuning_views.load_tuning_tab, name="loadTuningTab"),
    path('calibration/save_tuning_tab/', calibration_tuning_views.save_tuning_tab, name="saveTuningTab"),
    path('calibration/upload_user_parameters/', calibration_tuning_views.upload_user_parameters, name="uploadUserParameters"),

    ##################################
    # Optimizations/Metrics tab
    ##################################
    path('calibration/load_optimization_tab/', calibration_optimization_views.load_optimization_tab, name="loadOptimizationTab"),
    path('calibration/save_optimization_tab/', calibration_optimization_views.save_optimization_tab, name="saveOptimizationTab"),

    ##################################
    # Run tab
    ##################################
    path('calibration/get_status/', calibration_run_views.get_status, name="getStatus"),
    path('calibration/run_calibration/', calibration_run_views.run_calibration, name="runCalibration"),
    path('calibration/report_iteration/', calibration_run_views.report_iteration, name="reportIteration"),
    path('calibration/get_iteration/', calibration_run_views.get_iteration, name="getIteration"),
    path('calibration/cancel_job/', calibration_run_views.cancel_job, name="cancelJob"),
    path('calibration/get_job_data_dir/', calibration_run_views.get_job_dir, name="getJobDir"),
    path('calibration/calibration_job_slurm_callback/', calibration_run_views.calibration_job_slurm_callback, name="calibrationJobSlurmCallback"),
    path('calibration/validation_job_slurm_callback/', calibration_run_views.validation_job_slurm_callback, name="validationJobSlurmCallback"),

    ##################################
    # Evaluation
    ##################################
    path('calibration/get_calibration_data_by_iteration/', calibration_evaluation_views.get_calibration_data_by_iteration, name="getCalibrationDataByIteration"),
    path('calibration/get_logs/', calibration_evaluation_views.get_logs, name="getLogs"),

    # Testing
    path('calibration/process_calibration_output/', calibration_run_views.process_calibration_output, name="processCalibrationOutput"),

    ##################################
    # Import/Export
    ##################################
    path('calibration/export/', calibration_import_export_views.export_job, name="export"),
    path('calibration/import/', calibration_import_export_views.import_job, name="import"),

    ##################################
    # Swagger - drf_spectacular
    ##################################
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    ##################################
    # Testing
    ##################################
    path('calibration/get_slurm_token/', calibration_run_views.get_slurm_token, name="getSlurmToken"),
]
