import json
import sys


def check_http_error(http_status: int, response: str, exit_on_error: bool = False) -> bool:
    if http_status == 0:
        print("Error: Could not connect to the server.")
        if exit_on_error:
            sys.exit(1)
        return False
    elif http_status == 400:
        print("Server returned HTTP 400 Bad Request. Response:")
        _pretty_print_json(response)
        if exit_on_error:
            sys.exit(1)
        return False
    elif http_status != 200:
        print(f"Error: Server returned HTTP status code {http_status}. Response:")
        _pretty_print_json(response, suppress_html=(http_status == 404))
        if exit_on_error:
            sys.exit(1)
        return False

    # Don't print the response on 200
    return True


def _pretty_print_json(response: str, suppress_html: bool = False):
    try:
        parsed = json.loads(response)
        print(json.dumps(parsed, indent=3))
    except json.JSONDecodeError:
        if suppress_html:
            return  # do not print anything
        # print only the first 10 lines of non-JSON response
        lines = response.strip().splitlines()
        print("\n".join(lines[:10]) + ("\n..." if len(lines) > 10 else ""))
