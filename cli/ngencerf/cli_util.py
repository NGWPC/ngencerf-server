import json
import sys


def check_http_error(http_status: int, response: str) -> dict | None:
    """
    Handles HTTP errors, returning the parsed response for 200 status codes,
    and printing appropriate error messages for other status codes.

    :param http_status: The HTTP status code returned by the server.
    :param response: The raw response text from the server.
    :return: Parsed JSON response if the status code is 200, otherwise None.
    """
    try:
        # Treat 200 as success and return the parsed response
        if http_status == 200:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                print("Warning: Response is not valid JSON.")
                return None

        # Handle 400 Bad Request with specific error handling
        if http_status == 400:
            print("Server returned HTTP 400 Bad Request. Response:")
            response_json = json.loads(response)
            response_type = response_json.get("response_type", "")

            # Handle known response types separately
            if response_type == "error":
                print(response_json.get("message", "Unknown error occurred."))
            elif response_type == "validation_error":
                message = response_json.get("message", "Validation error occurred.")
                print(message)
                validation_errors = response_json.get("validation_errors", {})
                _print_validation_errors(validation_errors)
            else:
                _pretty_print_json(response)

            sys.exit(1)

        # Handle all other non-200 status codes
        try:
            response_json = json.loads(response)
            print(f"Error: Server returned HTTP status code {http_status}. Response:")
            _pretty_print_json(response)
        except json.JSONDecodeError:
            # Fallback for non-JSON responses
            print(f"Error: Server returned HTTP status code {http_status}. Response:")
            lines = response.strip().splitlines()
            print("\n".join(lines[:10]) + ("\n..." if len(lines) > 10 else ""))

        sys.exit(1)

    except json.JSONDecodeError:
        # Fallback to raw response if JSON parsing fails at the initial check
        print(f"Error: Server returned HTTP status code {http_status}. Response:")
        lines = response.strip().splitlines()
        print("\n".join(lines[:10]) + ("\n..." if len(lines) > 10 else ""))
        sys.exit(1)


def _print_validation_errors(errors: dict, prefix: str = "") -> None:
    """
    Recursively prints validation errors, handling both field-specific and nested errors.
    """
    for field, error_list in errors.items():
        # Handle nested dictionaries
        if isinstance(error_list, dict):
            _print_validation_errors(error_list, prefix=f"{prefix}{field}.")
        # Handle lists of errors
        elif isinstance(error_list, list):
            for error in error_list:
                # Handle nested error objects like ErrorDetail
                if isinstance(error, dict):
                    _print_validation_errors(error, prefix=f"{prefix}{field}.")
                else:
                    print(f"{prefix}{field}: {error}")
        else:
            print(f"{prefix}{field}: {error}")


def _pretty_print_json(response: str, suppress_html: bool = False):
    try:
        parsed = json.loads(response)
        print(json.dumps(parsed, indent=3))
    except json.JSONDecodeError:
        if suppress_html:
            return  # do not print anything for 404 HTML errors
        # print only the first 10 lines of non-JSON response
        lines = response.strip().splitlines()
        print("\n".join(lines[:10]) + ("\n..." if len(lines) > 10 else ""))
