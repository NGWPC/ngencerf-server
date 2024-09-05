import functools
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, Future

from calibration.util.ngen_locations import get_stdout_file

# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


def callback(filename, process_id, future: Future) -> None:
    # print('filename:', future.temp_file_name)
    try:
        if future.exception() is not None:
            print(f'Exception occurred in process {process_id}:', future.exception())
        else:
            print(f'Process {process_id} completed successfully with result:', future.result())

        with open(filename, 'r') as f:
            print(f"Output from {filename} for process {process_id}:")
            print(f.read())

    except Exception as e:
        print(f"Error in callback for process {process_id}: {e}")


# See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
# Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

def execute(run, args):
    python_output_filepath = get_stdout_file(run)
    process_id = f'{run.id}_{run.owner}'

    # Insert the output file path as the 2nd argument to the shell script
    args.insert(2, python_output_filepath)

    print(f"Spawning process: {process_id} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)
        future.add_done_callback(functools.partial(callback, python_output_filepath, process_id))
    except Exception as e:
        print(f"Failed to execute command: {e}")
        raise
    print(f'Submitted process {process_id}')
