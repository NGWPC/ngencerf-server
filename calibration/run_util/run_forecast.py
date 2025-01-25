# This module will be used to run the first stage of Forecast, which is the forcing download.
# It will *always* use the 'local' method of spawning a process to call the forcing script


def run_forecast_forcing():
    # Instead of calling execute_forecast_job, maybe call run_job_local directly, passing in our forecast_forcing_callback
    pass


def forecast_forcing_callback():
    # Handle the completion of the forcing download
    # Call the appropriate function to start the forecasting process, passing it the forcing file and any other input
    pass
