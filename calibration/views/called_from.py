import inspect
import logging
import os
from functools import cache  # Python 3.9+

logger = logging.getLogger(__name__)


@cache  # Cache the project root lookup
def get_project_root() -> str:
    """
    Finds the Django project root by searching for `manage.py`.
    We use this to avoid importing settings.py
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))  # Ensure we start from a directory

    while current_dir != os.path.dirname(current_dir):  # Stop at the filesystem root
        if "manage.py" in os.listdir(current_dir):
            return current_dir  # Found the project root
        current_dir = os.path.dirname(current_dir)  # Move up one level

    return os.getcwd()  # Fallback (shouldn't happen)


BASE_DIR = get_project_root()


def called_from() -> str:
    stack = inspect.stack()

    if len(stack) < 3:
        return "Unknown caller (not enough stack frames)"

    caller_frame = stack[2]  # The function that called the function calling `called_from()`
    caller_name = caller_frame.function
    caller_filename = caller_frame.filename
    caller_lineno = caller_frame.lineno

    # Convert absolute path to relative path, ensuring it's within BASE_DIR
    relative_path = os.path.relpath(caller_filename, BASE_DIR)

    return f'called from {caller_name} in {relative_path}:{caller_lineno}'
