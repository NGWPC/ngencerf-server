import multiprocessing
import os
import subprocess


# From https://stackoverflow.com/questions/2581817/python-subprocess-callback-when-cmd-exits
class Process(object):
    """This class spawns a subprocess asynchronously and calls a
    `callback` upon completion; it is not meant to be instantiated
    directly (derived classes are called instead)"""

    def __call__(self, *args):
        # store the arguments for later retrieval
        self.args = args

        # define the target function to be called by
        # `multiprocessing.Process`
        def target():
            cmd = [self.command] + [str(arg) for arg in self.args]
            print('cmd', cmd)
            process = subprocess.Popen(cmd)
            # the `multiprocessing.Process` process will wait until
            # the call to the `subprocess.Popen` object is completed
            process.wait()
            # upon completion, call `callback`
            return self.callback()

        mp_process = multiprocessing.Process(target=target)
        # this call issues the call to `target`, but returns immediately
        mp_process.start()
        return mp_process


if __name__ == "__main__":
    def squeal(who):
        """this serves as the callback function; its argument is the
        instance of a subclass of Process making the call"""
        print("finished %s calling %s with arguments %s" % (who.__class__.__name__, who.command, who.args))


    class Sleeper(Process):
        """Sample implementation of an asynchronous process - define
        the command name (available in the system path) and a callback
        function (previously defined)"""
        command = os.path.expanduser("~/testSpawn.sh")
        callback = squeal


    # create an instance to Sleeper - this is the Process object that
    # can be called repeatedly in an asynchronous manner
    sleeper_run = Sleeper()

    # spawn three sleeper runs with different arguments
    sleeper_run(5)
    sleeper_run(2)
    sleeper_run(1)

    # the user should see the following message immediately (even
    # though the Sleeper calls are not done yet)
    print("program continued")
