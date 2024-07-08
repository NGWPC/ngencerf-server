from django.urls import path

from calibration import calibration_gage_views, calibration_formulation_views, calibration_landing_views

urlpatterns = [

    path('calibration/create_calibration_run/', calibration_landing_views.create_calibration_run, name="createCalibrationRun"),
    path('calibration/get_gage/<str:gage_id>/', calibration_gage_views.get_gage, name="getGage"),
    path('calibration/get_gage/', calibration_gage_views.get_gage, name="getGage_post"),
    path('calibration/get_gages/', calibration_gage_views.get_gages, name="getGages"),
    path('calibration/save_gage_tab/', calibration_gage_views.save_gage_tab, name="saveGageTab"),
    path('calibration/csrf/', calibration_gage_views.csrf, name="csrf"),

    path('calibration/get_modules/<str:calibration_run_id>/', calibration_formulation_views.get_modules, name="getModules"),
    path('calibration/get_modules/', calibration_formulation_views.get_modules, name="getModules_post"),
    path('calibration/save_formulation_tab/', calibration_formulation_views.save_formulation_tab, name="saveFormulationTab"),
]
