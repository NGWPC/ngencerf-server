from django.urls import path

from views import calibration_formulation_views, calibration_gage_views, calibration_landing_views, \
    calibration_optimization_views, calibration_metrics_views

urlpatterns = [

    ##################################
    # Landing page
    ##################################
    path('calibration/create_calibration_run/', calibration_landing_views.create_calibration_run, name="createCalibrationRun"),

    ##################################
    # Gage tab
    ##################################
    path('calibration/get_gage/', calibration_gage_views.get_gage, name="getGage_post"),
    path('calibration/get_gages/', calibration_gage_views.get_gages, name="getGages"),
    path('calibration/save_gage_tab/', calibration_gage_views.save_gage_tab, name="saveGageTab"),
    path('calibration/csrf/', calibration_gage_views.csrf, name="csrf"),

    ##################################
    # Formulation tab
    ##################################
    path('calibration/get_modules/', calibration_formulation_views.get_modules, name="getModules_post"),
    path('calibration/save_formulation_tab/', calibration_formulation_views.save_formulation_tab, name="saveFormulationTab"),

    ##################################
    # Optimizations tab
    ##################################
    path('calibration/get_optimizations/', calibration_optimization_views.get_optimizations, name="getOptimizations"),

    ##################################
    # Metrics tab
    ##################################
    path('calibration/get_metrics/', calibration_metrics_views.get_metrics, name="getMetrics"),
]
