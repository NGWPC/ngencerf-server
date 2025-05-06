import getpass
import os

import requests

from ngencerf.cli_util import check_http_error

LOGIN_ENDPOINT = "http://localhost:8000/auth/jwt/create"
REGISTER_ENDPOINT = "http://localhost:8000/auth/users/"
ENV_FILE = os.path.join(os.path.expanduser("~"), ".ngencerf_env")


def save_to_env_file(key: str, value: str):
    """
    Save or update a key-value pair in ~/.ngencerf_env without duplication.

    If the key already exists, its value is updated. Otherwise, it's appended.
    """
    lines = []

    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        found = False
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"{key}={value}\n")


def load_ngencerf_env():
    """
    Load variables from ~/.ngencerf_env into the environment if not already present.
    Ignores comments and blank lines.
    """
    if not os.path.exists(ENV_FILE):
        return

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in os.environ:
                os.environ[key] = value


def save_credentials_to_env_file(email: str, password: str):
    """
    Persist email and password to ~/.ngencerf_env so user isn't prompted every time.
    """
    save_to_env_file("NGEN_EMAIL", email)
    save_to_env_file("NGEN_PASSWORD", password)


def ngen_login():
    """
    Logs in to the NGEN API, storing ACCESS_TOKEN in the environment.

    If NGEN_EMAIL and NGEN_PASSWORD are not set, the user is prompted.
    Credentials are saved to ~/.ngencerf_env for reuse.
    """
    load_ngencerf_env()

    email = os.environ.get("NGEN_EMAIL") or os.environ.get("NGEN_USERNAME")
    if not email:
        email = input("ngenCerf email: ")

    password = os.environ.get("NGEN_PASSWORD")
    if not password:
        password = getpass.getpass("ngenCerf password: ")

    payload = {"email": email, "password": password}
    response = requests.post(LOGIN_ENDPOINT, json=payload)

    if response.status_code != 200:
        check_http_error(response.status_code, response.text, exit_on_error=True)
        return

    access_token = response.json().get("access")
    if access_token:
        os.environ["ACCESS_TOKEN"] = access_token
        os.environ["NGEN_EMAIL"] = email
        os.environ["NGEN_PASSWORD"] = password
        save_credentials_to_env_file(email, password)
        print(f"{email} login successful.\n")
    else:
        print("Login succeeded, but access token missing.")


def ngen_register(optional_email: str = None):
    """
    Registers a new user for the NGEN API. Prompts for password input and confirmation.
    """
    email = optional_email or os.environ.get("NGEN_EMAIL") or os.environ.get("NGEN_USERNAME")
    if not email:
        email = input("Enter a new email for ngenCerf registration: ")

    while True:
        password = getpass.getpass("Enter a new password for ngenCerf registration: ")
        password_confirm = getpass.getpass("Confirm your password: ")
        if password == password_confirm:
            break
        print("Passwords do not match. Please try again.")

    payload = {
        "email": email,
        "password": password,
        "re_password": password_confirm,
    }

    response = requests.post(REGISTER_ENDPOINT, json=payload)
    if check_http_error(response.status_code, response.text, exit_on_error=True):
        print(f"User '{email}' registered successfully.")
