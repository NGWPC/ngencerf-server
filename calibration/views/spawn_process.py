import functools
import os.path
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future

from calibration.models import CalibrationRun

# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


# See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
# Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future


def execute(run: CalibrationRun, current_stage, args, callback_function):
    process_id = os.path.basename(run.job_data_dir)

    print(f"Spawning process: {process_id} in stage {current_stage.name} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)
        future.add_done_callback(functools.partial(callback, process_id, current_stage, callback_function))
    except Exception as e:
        print(f"Failed to execute command: {str(e)}")
        raise
    print(f'Process {process_id} in stage {current_stage.name} is running in the background')


def callback(process_id, job_stage, callback_function, future: Future) -> None:
    # print('filename:', future.temp_file_name)
    try:
        if future.exception() is not None:
            print(f'Exception occurred in process {process_id} at stage {job_stage.name}:', future.exception())
        else:
            exit_code = future.result()

            print(f'Process {process_id}, stage {job_stage.name}, completed successfully with exit code {exit_code}')

        print('------------------------------------------------')
        print(f'Running callback function for {process_id} at stage {job_stage.name}')
        # Arguments have already been defined in functools.partial
        callback_function()

    except Exception as e:
        print(f"Error in callback for process {process_id} at stage {job_stage.name}: {str(e)}")
