from django.urls import path

from calibration import calibration_views

urlpatterns = [
    # path('', calibration_views.test, name="test"),
    path('calibration/get_modules/', calibration_views.get_modules, name="getModules"),
    path('calibration/get_gage/<str:gage_id>', calibration_views.get_gage, name="getGage"),
    path('calibration/get_gage/', calibration_views.get_gage, name="getGage_post"),
    path('calibration/get_gages/', calibration_views.get_gages, name="getGages"),
    path('calibration/save_tab1/', calibration_views.save_tab1, name="saveTab1")
]
