import os
from logging.handlers import TimedRotatingFileHandler


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=7, encoding='utf-8'):
        super().__init__(filename, when=when, interval=interval, backupCount=backupCount, encoding=encoding)

    def rotation_filename(self, default_name):
        # Override this method to customize the log file name
        # Strip the existing date format and replace it with the desired format
        dir_name, base_filename = os.path.split(self.baseFilename)
        log_filename = base_filename.split('.')[0]  # Remove the .log part
        date_suffix = self.extMatch.match(default_name).group(0)
        new_filename = f"{log_filename}_{date_suffix}.log"
        return os.path.join(dir_name, new_filename)
