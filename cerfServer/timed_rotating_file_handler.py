import os
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, IO


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    stream: Optional[IO] = None

    def __init__(self, filename, when='midnight', interval=1, backupCount=7, encoding='utf-8'):
        super().__init__(filename, when=when, interval=interval, backupCount=backupCount, encoding=encoding)

    def doRollover(self):
        """
        Overriding doRollover to rename the log files with the desired format.
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        # Get the time when this log file was created
        current_time = self.rolloverAt - self.interval
        time_tuple = self.utc and time.gmtime(current_time) or time.localtime(current_time)

        # Get the base log filename and directory
        dir_name, base_filename = os.path.split(self.baseFilename)
        log_filename, log_extension = os.path.splitext(base_filename)

        # Format the date and insert it before the extension
        date_suffix = time.strftime("%Y-%m-%dT%H:%M:%S", time_tuple)
        new_filename = f"{log_filename}.{date_suffix}{log_extension}"

        # Rename the current log file to the new filename
        dfn = Path(dir_name) / new_filename
        if Path(self.baseFilename).exists():
            os.rename(self.baseFilename, dfn)

        # Handle file rotation
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                try:
                    os.remove(s)
                except FileNotFoundError:
                    pass

        # Reopen the file for the new log entries
        self.mode = 'w'
        self.stream = self._open()

        # Update the rollover time for the next interval
        new_rollover_at = self.computeRollover(self.rolloverAt)
        while new_rollover_at <= current_time:
            new_rollover_at += self.interval
        self.rolloverAt = new_rollover_at
