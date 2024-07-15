import os
import subprocess
import tempfile


def callback(future):
    print(future.temp_file_name)
    try:
        with open(future.temp_file_name, 'r') as f:
            print(f"Output from {future.temp_file_name}:")
            print(f.read())
    except Exception as e:
        print(f"Error in callback: {e}")


# See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
# Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

def execute(args):
    from concurrent.futures import ProcessPoolExecutor as Pool

    args[0] = os.path.expanduser(args[0])
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_name = temp_file.name

        print('temp_file_name', temp_file_name)

        pool = Pool()
        with open(temp_file_name, 'w') as output_file:
            process = subprocess.Popen(args, stdout=output_file, stderr=output_file)
            future = pool.submit(process.wait)
            future.temp_file_name = temp_file_name
            future.add_done_callback(callback)

            print("Running task")


if __name__ == '__main__':

    execute(['~/testSpawn.sh', '1'])
    execute(['~/testSpawn.sh', '2'])
    execute(['~/testSpawn.sh', '3'])
