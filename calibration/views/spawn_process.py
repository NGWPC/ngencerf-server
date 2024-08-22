import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, Future


def callback(future: Future) -> None:
    # print('filename:', future.temp_file_name)
    try:
        if future.exception() is not None:
            print('exception:', future.exception())
        else:
            print('result:', future.result())
        if hasattr(future, 'temp_file_name'):
            with open(future.temp_file_name, 'r') as f:
                print(f"Output from {future.temp_file_name}:")
                print('data:', f.read())
        else:
            print("No temp_file_name attribute found on the future object.")
    except Exception as e:
        print(f"Error in callback: {e}")


# See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
# Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

def execute(args):
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_name = temp_file.name

        pool = ThreadPoolExecutor()
        with open(temp_file_name, 'w') as output_file:
            process = subprocess.Popen(args, stdout=output_file, stderr=output_file)
            future = pool.submit(process.wait)
            future.temp_file_name = temp_file_name
            future.add_done_callback(callback)
            # pool.shutdown(wait=False)

            print("Running task")
