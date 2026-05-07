import os

ENV_FILE = os.path.join(os.path.expanduser("~"), ".ngencerf_env")
DEFAULT_NGENCERF_BASE_URL = "http://localhost:8000"
NGENCERF_BASE_URL_KEY = "NGENCERF_BASE_URL"


def load_ngencerf_env() -> None:
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


def save_to_env_file(key: str, value: str) -> None:
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


def remove_from_env_file(keys: set[str]) -> None:
    for key in keys:
        os.environ.pop(key, None)

    if not os.path.exists(ENV_FILE):
        return

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            if not any(line.startswith(f"{key}=") for key in keys):
                f.write(line)


def get_ngencerf_base_url() -> str:
    load_ngencerf_env()
    return os.environ.get(NGENCERF_BASE_URL_KEY, DEFAULT_NGENCERF_BASE_URL).rstrip("/")


def set_ngencerf_base_url(base_url: str) -> None:
    base_url = base_url.strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Server URL must start with http:// or https://")

    os.environ[NGENCERF_BASE_URL_KEY] = base_url
    save_to_env_file(NGENCERF_BASE_URL_KEY, base_url)

    # Tokens are server-specific. Clear them whenever setup writes the server URL.
    remove_from_env_file({"ACCESS_TOKEN", "REFRESH_TOKEN"})


def show_ngencerf_base_url() -> None:
    print(f"Current ngenCerf server: {get_ngencerf_base_url()}")