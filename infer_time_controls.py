#!/usr/bin/env python3
"""
Infer ngenCerf time controls from legacy calibration and validation time ranges.

Accepted JSON
-------------

The input may contain the ranges directly:

    {
        "calibration_times": {
            "simulation_start_time": "2016-10-01T00:00:00+00:00",
            "simulation_end_time": "2017-09-30T23:00:00+00:00",
            "calibration_start_time": "2017-04-01T00:00:00+00:00",
            "calibration_end_time": "2017-09-30T23:00:00+00:00"
        },
        "validation_times": {
            "simulation_start_time": "2016-10-01T00:00:00+00:00",
            "simulation_end_time": "2018-03-31T23:00:00+00:00",
            "validation_start_time": "2017-10-01T00:00:00+00:00",
            "validation_end_time": "2018-03-31T23:00:00+00:00"
        }
    }

The input may also be a complete exported job with the same objects under
``metadata``:

    {
        "metadata": {
            "calibration_times": { ... },
            "validation_times": { ... }
        }
    }

Usage
-----

Read a file:

    python infer_time_controls.py ranges.json

Read redirected or piped stdin:

    python infer_time_controls.py < ranges.json
    cat ranges.json | python infer_time_controls.py

Paste interactively when no file or redirected stdin is provided:

    python infer_time_controls.py

In interactive mode, paste the complete JSON object. The program continues as
soon as the pasted text is complete. If needed, end input with Ctrl-D on
Linux/macOS or Ctrl-Z followed by Enter on Windows.

Output
------

The inferred controls are written to stdout as valid JSON, so they may be
redirected directly to a file:

    python infer_time_controls.py ranges.json > time_controls.json

Messages explaining timezone assumptions, boundary interpretations, rounding,
ambiguous validation placement, or inconsistent legacy ranges are written to
stderr. They remain visible in the terminal and do not corrupt redirected JSON.

Inference rules and assumptions
-------------------------------

* ``simulation_start_time`` is the calibration simulation start.
* ``warmup_duration`` is the number of calendar months from the calibration
  simulation start to the calibration evaluation start.
* Calibration and validation durations are whole calendar months.
* Evaluation ends normally use the current inclusive 23:00 convention. Exact
  exclusive 00:00 boundaries are also accepted.
* Validation placement is inferred from the relative evaluation periods.
* The validation gap is the number of calendar months between evaluation
  periods.
* Irregular legacy timestamps are rounded to the nearest non-negative whole
  calendar month, and every non-exact decision is reported.
* If validation placement is ambiguous, both before-calibration and
  after-calibration models are scored; the model requiring the smaller total
  timestamp adjustment is selected.
* Timestamps without timezone information are treated as UTC and reported.
* Simulation-range inconsistencies do not prevent output; they are reported for
  review.

Expected output
---------------

    {
        "simulation_start_time": "2016-10-01T00:00:00Z",
        "warmup_duration": 6,
        "calibration_duration": 6,
        "validation_window_gap": 0,
        "validation_window_after_calibration": true,
        "validation_duration": 6
    }

Exit status
-----------

* 0: Controls were produced, including cases with explanatory messages.
* 1: Input was missing, invalid, or lacked required fields.
* 2: Command-line usage was invalid.

The program uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CALIBRATION_FIELDS = (
    "simulation_start_time",
    "simulation_end_time",
    "calibration_start_time",
    "calibration_end_time",
)

VALIDATION_FIELDS = (
    "simulation_start_time",
    "simulation_end_time",
    "validation_start_time",
    "validation_end_time",
)


@dataclass(frozen=True)
class MonthMatch:
    months: int
    expected: datetime
    compared: datetime
    error: timedelta
    interpretation: str


@dataclass(frozen=True)
class Orientation:
    after_calibration: bool
    gap: MonthMatch
    expected_simulation_start: datetime
    expected_simulation_end: datetime
    score: timedelta


def absolute_delta(value: timedelta) -> timedelta:
    return value if value >= timedelta(0) else -value


def format_duration(value: timedelta) -> str:
    seconds = absolute_delta(value).total_seconds()
    if seconds == 0:
        return "0 seconds"

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts: list[str] = []
    for amount, unit in (
        (days, "day"),
        (hours, "hour"),
        (minutes, "minute"),
        (seconds, "second"),
    ):
        if amount:
            parts.append(
                f"{amount:g} {unit}{'' if amount == 1 else 's'}"
            )

    return ", ".join(parts)


def parse_datetime(
    value: Any,
    name: str,
    messages: list[str],
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty ISO-8601 string"
        )

    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{name} is not a valid ISO-8601 datetime: {value!r}"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
        messages.append(
            f"Assumed UTC for {name} because no timezone was supplied."
        )

    return parsed


def format_datetime(value: datetime) -> str:
    if value.utcoffset() == timedelta(0):
        return (
            value.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    return value.isoformat()


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(
        value.day,
        calendar.monthrange(year, month)[1],
    )

    return value.replace(
        year=year,
        month=month,
        day=day,
    )


def nearest_month_match(
    start: datetime,
    target: datetime,
    *,
    evaluation_end: bool = False,
) -> MonthMatch:
    candidates = [
        (target, "exclusive boundary"),
    ]

    if evaluation_end:
        candidates.append(
            (
                target + timedelta(hours=1),
                "inclusive 23:00 end",
            )
        )

    best: MonthMatch | None = None

    for compared, interpretation in candidates:
        rough = (
            (compared.year - start.year) * 12
            + compared.month
            - start.month
        )

        for months in range(
            max(0, rough - 2),
            max(0, rough + 2) + 1,
        ):
            expected = add_months(start, months)

            match = MonthMatch(
                months=months,
                expected=expected,
                compared=compared,
                error=absolute_delta(expected - compared),
                interpretation=interpretation,
            )

            if best is None or match.error < best.error:
                best = match
            elif (
                match.error == best.error
                and interpretation == "inclusive 23:00 end"
            ):
                best = match

    assert best is not None
    return best


def report_month_match(
    messages: list[str],
    control: str,
    start: datetime,
    supplied: datetime,
    match: MonthMatch,
    *,
    evaluation_end: bool = False,
) -> None:
    if (
        evaluation_end
        and match.interpretation == "exclusive boundary"
        and not match.error
    ):
        messages.append(
            f"Interpreted {control} using an exclusive 00:00 boundary "
            "rather than the current inclusive 23:00 convention."
        )

    if match.error:
        messages.append(
            f"Rounded {control} to {match.months} whole calendar "
            f"month(s). Starting at {format_datetime(start)}, the "
            f"supplied timestamp {format_datetime(supplied)} was "
            f"treated as {match.interpretation}; its effective "
            f"boundary {format_datetime(match.compared)} differs "
            f"from the nearest month boundary "
            f"{format_datetime(match.expected)} by "
            f"{format_duration(match.error)}."
        )


def read_ranges(
    payload: Any,
    messages: list[str],
) -> tuple[dict[str, datetime], dict[str, datetime]]:
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")

    container = payload.get("metadata")
    if not isinstance(container, dict):
        container = payload

    def read_object(
        name: str,
        fields: tuple[str, ...],
    ) -> dict[str, datetime]:
        raw = container.get(name)
        if not isinstance(raw, dict):
            raise ValueError(
                f"{name} must be a JSON object"
            )

        missing = [
            field
            for field in fields
            if raw.get(field) is None
        ]

        if missing:
            raise ValueError(
                f"{name} is missing required field(s): "
                f"{', '.join(missing)}"
            )

        return {
            field: parse_datetime(
                raw[field],
                f"{name}.{field}",
                messages,
            )
            for field in fields
        }

    return (
        read_object(
            "calibration_times",
            CALIBRATION_FIELDS,
        ),
        read_object(
            "validation_times",
            VALIDATION_FIELDS,
        ),
    )


def orientation_candidate(
    *,
    after_calibration: bool,
    calibration_simulation_start: datetime,
    calibration_evaluation_start: datetime,
    calibration_end_boundary: datetime,
    calibration_end_supplied: datetime,
    validation_simulation_start: datetime,
    validation_simulation_end: datetime,
    validation_evaluation_start: datetime,
    validation_end_boundary: datetime,
    validation_end_supplied: datetime,
    warmup_months: int,
) -> Orientation:
    if after_calibration:
        gap = nearest_month_match(
            calibration_end_boundary,
            validation_evaluation_start,
        )

        expected_start = calibration_simulation_start
        expected_end = validation_end_supplied

    else:
        gap = nearest_month_match(
            validation_end_boundary,
            calibration_evaluation_start,
        )

        expected_start = add_months(
            validation_evaluation_start,
            -warmup_months,
        )
        expected_end = calibration_end_supplied

    score = (
        gap.error
        + absolute_delta(
            validation_simulation_start - expected_start
        )
        + absolute_delta(
            validation_simulation_end - expected_end
        )
    )

    return Orientation(
        after_calibration=after_calibration,
        gap=gap,
        expected_simulation_start=expected_start,
        expected_simulation_end=expected_end,
        score=score,
    )


def report_mismatch(
    messages: list[str],
    label: str,
    supplied: datetime,
    used: datetime,
) -> None:
    difference = absolute_delta(supplied - used)

    if difference:
        messages.append(
            f"{label} is inconsistent with the inferred controls. "
            f"Received {format_datetime(supplied)}; "
            f"used {format_datetime(used)} instead "
            f"(difference: {format_duration(difference)})."
        )


def reconstruct_controls(
    calibration: dict[str, datetime],
    validation: dict[str, datetime],
    messages: list[str],
) -> dict[str, Any]:
    cal_sim_start = calibration[
        "simulation_start_time"
    ]
    cal_sim_end = calibration[
        "simulation_end_time"
    ]
    cal_start = calibration[
        "calibration_start_time"
    ]
    cal_end = calibration[
        "calibration_end_time"
    ]

    val_sim_start = validation[
        "simulation_start_time"
    ]
    val_sim_end = validation[
        "simulation_end_time"
    ]
    val_start = validation[
        "validation_start_time"
    ]
    val_end = validation[
        "validation_end_time"
    ]

    warmup = nearest_month_match(
        cal_sim_start,
        cal_start,
    )

    cal_duration = nearest_month_match(
        cal_start,
        cal_end,
        evaluation_end=True,
    )

    val_duration = nearest_month_match(
        val_start,
        val_end,
        evaluation_end=True,
    )

    report_month_match(
        messages,
        "warmup_duration",
        cal_sim_start,
        cal_start,
        warmup,
    )

    report_month_match(
        messages,
        "calibration_duration",
        cal_start,
        cal_end,
        cal_duration,
        evaluation_end=True,
    )

    report_month_match(
        messages,
        "validation_duration",
        val_start,
        val_end,
        val_duration,
        evaluation_end=True,
    )

    after = orientation_candidate(
        after_calibration=True,
        calibration_simulation_start=cal_sim_start,
        calibration_evaluation_start=cal_start,
        calibration_end_boundary=cal_duration.expected,
        calibration_end_supplied=cal_end,
        validation_simulation_start=val_sim_start,
        validation_simulation_end=val_sim_end,
        validation_evaluation_start=val_start,
        validation_end_boundary=val_duration.expected,
        validation_end_supplied=val_end,
        warmup_months=warmup.months,
    )

    before = orientation_candidate(
        after_calibration=False,
        calibration_simulation_start=cal_sim_start,
        calibration_evaluation_start=cal_start,
        calibration_end_boundary=cal_duration.expected,
        calibration_end_supplied=cal_end,
        validation_simulation_start=val_sim_start,
        validation_simulation_end=val_sim_end,
        validation_evaluation_start=val_start,
        validation_end_boundary=val_duration.expected,
        validation_end_supplied=val_end,
        warmup_months=warmup.months,
    )

    clearly_after = (
        val_start >= cal_duration.expected
    )
    clearly_before = (
        cal_start >= val_duration.expected
    )

    if clearly_after and not clearly_before:
        orientation = after

    elif clearly_before and not clearly_after:
        orientation = before

    else:
        orientation = min(
            (after, before),
            key=lambda item: item.score,
        )

        messages.append(
            "The evaluation periods did not establish an "
            "unambiguous validation position. Both models were "
            "scored, and validation_window_after_calibration="
            f"{str(orientation.after_calibration).lower()} was "
            "selected because it required the smaller total "
            "timestamp adjustment."
        )

    gap_start = (
        cal_duration.expected
        if orientation.after_calibration
        else val_duration.expected
    )

    gap_target = (
        val_start
        if orientation.after_calibration
        else cal_start
    )

    report_month_match(
        messages,
        "validation_window_gap",
        gap_start,
        gap_target,
        orientation.gap,
    )

    report_mismatch(
        messages,
        "Calibration simulation_end_time",
        cal_sim_end,
        cal_end,
    )

    report_mismatch(
        messages,
        "Validation simulation_start_time",
        val_sim_start,
        orientation.expected_simulation_start,
    )

    report_mismatch(
        messages,
        "Validation simulation_end_time",
        val_sim_end,
        orientation.expected_simulation_end,
    )

    return {
        "simulation_start_time": format_datetime(
            cal_sim_start
        ),
        "warmup_duration": warmup.months,
        "calibration_duration": cal_duration.months,
        "validation_window_gap": orientation.gap.months,
        "validation_window_after_calibration": (
            orientation.after_calibration
        ),
        "validation_duration": val_duration.months,
    }


def try_parse_complete_json(
    text: str,
) -> tuple[bool, Any]:
    stripped = text.lstrip()

    if not stripped:
        return False, None

    try:
        value, end = (
            json.JSONDecoder()
            .raw_decode(stripped)
        )
    except json.JSONDecodeError:
        return False, None

    return (
        not stripped[end:].strip(),
        value,
    )


def load_interactive_json() -> Any:
    print(
        "Paste the JSON input below.",
        file=sys.stderr,
    )
    print(
        "The program will continue automatically when valid JSON is complete.",
        file=sys.stderr,
    )
    print(
        "Alternatively, enter END on a separate line to finish input.",
        file=sys.stderr,
    )

    lines: list[str] = []

    while True:
        try:
            line = input("> " if not lines else "  ")
        except EOFError:
            break
        except KeyboardInterrupt as exc:
            print(file=sys.stderr)
            raise ValueError("Input cancelled") from exc

        if line.strip().upper() == "END":
            break

        lines.append(line)

        complete, value = try_parse_complete_json(
            "\n".join(lines)
        )

        if complete:
            return value

    text = "\n".join(lines).strip()

    if not text:
        raise ValueError("No JSON input was provided")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid pasted JSON: {exc}"
        ) from exc


def load_json(
    input_path: str | None,
) -> Any:
    if input_path == "-":
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON from stdin: {exc}"
            ) from exc

    if input_path is None:
        if sys.stdin.isatty():
            return load_interactive_json()

        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON from stdin: {exc}"
            ) from exc

    try:
        with Path(input_path).open(
            "r",
            encoding="utf-8",
        ) as input_file:
            return json.load(input_file)

    except FileNotFoundError as exc:
        raise ValueError(
            f"Input file does not exist: {input_path}"
        ) from exc

    except OSError as exc:
        raise ValueError(
            f"Unable to read {input_path}: {exc}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {input_path}: {exc}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Infer ngenCerf time controls from legacy "
            "calibration and validation time ranges."
        ),
        formatter_class=(
            argparse.RawDescriptionHelpFormatter
        ),
        epilog=(
            "Examples:\n"
            "  python infer_time_controls.py ranges.json\n"
            "  python infer_time_controls.py < ranges.json\n"
            "  python infer_time_controls.py\n\n"
            "With no file and no redirected stdin, paste JSON "
            "at the prompt.\n"
            "Controls go to stdout; explanatory messages go "
            "to stderr."
        ),
    )

    parser.add_argument(
        "input",
        nargs="?",
        help=(
            "JSON input file. Use '-' for stdin. When omitted, "
            "redirected stdin is read automatically or "
            "interactive paste mode is used."
        ),
    )

    args = parser.parse_args()

    messages: list[str] = []

    try:
        payload = load_json(
            args.input
        )

        calibration, validation = read_ranges(
            payload,
            messages,
        )

        controls = reconstruct_controls(
            calibration,
            validation,
            messages,
        )

    except (
        ValueError,
        TypeError,
        OverflowError,
    ) as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    if sys.stdout.isatty():
        print("\n--- Inferred time controls JSON ---")

    json.dump(
        controls,
        sys.stdout,
        indent=4,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()

    if messages:
        print(
            "\nInference messages:",
            file=sys.stderr,
        )

        for message in messages:
            print(
                f"  - {message}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())