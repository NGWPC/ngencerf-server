import functools
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future

from calibration.models import CalibrationRun

# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


# See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
# Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

def execute(run: CalibrationRun, args, validation_callback=None):
    process_id = f'{run.id}_{run.owner}'

    print(f"Spawning process: {process_id} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)
        future.add_done_callback(functools.partial(callback, run, process_id, validation_callback))
    except Exception as e:
        print(f"Failed to execute command: {e}")
        raise
    print(f'Submitted process {process_id}')


def callback(run: CalibrationRun, process_id, validation_callback, future: Future) -> None:
    # print('filename:', future.temp_file_name)
    try:
        if future.exception() is not None:
            print(f'Exception occurred in process {process_id}:', future.exception())
        else:
            print(f'Process {process_id} completed successfully with result:', future.result())

        if validation_callback:
            print('------------------------------------------------')
            print(f'Running validation for {process_id}')
            validation_callback(run)

    except Exception as e:
        print(f"Error in callback for process {process_id}: {e}")
