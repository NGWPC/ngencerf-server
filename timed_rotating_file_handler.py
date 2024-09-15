import os
from logging.handlers import TimedRotatingFileHandler


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=7, encoding='utf-8'):
        super().__init__(filename, when=when, interval=interval, backupCount=backupCount, encoding=encoding)

    def rotation_filename(self, default_name):
        # Check if extMatch returns None, and handle it gracefully
        if self.extMatch is not None:
            match = self.extMatch.match(default_name)
            if match:
                # Get the date suffix from the match
                date_suffix = match.group(0)
                # Strip the existing extension and add the new format
                dir_name, base_filename = os.path.split(self.baseFilename)
                log_filename = base_filename.split('.')[0]  # Remove the .log part
                new_filename = f"{log_filename}_{date_suffix}.log"
                return os.path.join(dir_name, new_filename)

        # Fallback if extMatch fails
        return default_name