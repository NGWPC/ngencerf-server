from django.urls import path

from calibration import calibration_views

urlpatterns = [
    path('', calibration_views.test, name="test"),
    path('get_modules/', calibration_views.get_modules, name="getModules"),
    path('get_gage/<str:gage_id>', calibration_views.get_gage, name="getGage"),
    path('get_gage/', calibration_views.get_gage, name="getGage_post"),
    path('get_gages/', calibration_views.get_gages, name="getGages")
]
