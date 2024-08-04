from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from calibration.views import calibration_formulation_views, calibration_tuning_views, calibration_api_views, calibration_landing_views, \
    calibration_gage_views, calibration_optimization_views, calibration_run_views

urlpatterns = [
    ##################################
    # Api page
    ##################################
    path('calibration/report_iteration/', calibration_api_views.report_iteration, name="reportIteration"),

    ##################################
    # Landing page
    ##################################
    path('calibration/create_calibration_run/', calibration_landing_views.create_calibration_run, name="createCalibrationRun"),
    path('calibration/get_footer/', calibration_landing_views.get_footer, name="getFooter"),
    path('calibration/get_jobs/', calibration_landing_views.get_jobs, name="getJobs"),

    ##################################
    # Gage tab
    ##################################
    path('calibration/get_gage/', calibration_gage_views.get_gage, name="getGage"),
    path('calibration/get_gages/', calibration_gage_views.get_gages, name="getGages"),
    path('calibration/load_gage_tab/', calibration_gage_views.load_gage_tab, name="loadGageTab"),
    path('calibration/upload_observational_data/', calibration_gage_views.upload_observational_data, name="uploadObservationalData"),
    path('calibration/upload_forcing_data/', calibration_gage_views.upload_forcing_data, name="uploadForcingData"),
    path('calibration/save_gage_tab/', calibration_gage_views.save_gage_tab, name="saveGageTab"),

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

    ##################################
    # Optimizations/Metrics tab
    ##################################
    path('calibration/load_optimization_tab/', calibration_optimization_views.load_optimization_tab, name="loadOptimizationTab"),
    path('calibration/save_optimization_tab/', calibration_optimization_views.save_optimization_tab, name="saveOptimizationTab"),

    ##################################
    # Run tab
    ##################################
    path('calibration/is_ready/', calibration_run_views.is_ready, name="isReady"),
    path('calibration/run_calibration/', calibration_run_views.run_calibration, name="runCalibration"),

    ##################################
    # Swagger - drf_spectacular
    ##################################
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
