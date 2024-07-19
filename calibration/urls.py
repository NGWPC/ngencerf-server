from django.urls import path

from views import calibration_formulation_views, calibration_gage_views, calibration_landing_views, \
    calibration_optimization_views, calibration_tuning_views, calibration_api_views
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
    path('calibration/get_gage/', calibration_gage_views.get_gage, name="getGage_post"),
    path('calibration/load_gage_tab/', calibration_gage_views.load_gage_tab, name="loadGageTab"),
    path('calibration/save_gage_tab/', calibration_gage_views.save_gage_tab, name="saveGageTab"),
    path('calibration/csrf/', calibration_gage_views.csrf, name="csrf"),

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
    path('calibration/get_optimizations/', calibration_optimization_views.get_optimizations, name="getOptimizations"),
    path('calibration/get_metrics/', calibration_optimization_views.get_metrics, name="getMetrics"),
    path('calibration/save_optimization_tab/', calibration_optimization_views.save_optimization_tab, name="saveOptimizationTab"),

]
