# calibration/management/commands/data_validation.py
import csv
import os
import sys
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from calibration.enums import ValidationType
from calibration.models import ValidationRun, ValidationMetrics, Iteration


def print_flush(msg, file=sys.stdout):
    now = datetime.now(timezone.utc).isoformat()
    print(f"{now} - {msg}", file=file, flush=True)


def export_validation_metrics_csv(calibration_run_ids: list[int], out_path: str) -> None:
    """
    Export a single wide CSV for the union of metrics across all VALID_BEST ValidationRuns
    for the given calibration_run_ids.

    Columns: calibration_run_id, validation_run_id, gage_id, formulation, evalPeriod, <metric_1>, <metric_2>, ...
    One row per (calibration_run_id, evalPeriod).
    """
    if not calibration_run_ids:
        raise ValueError("calibration_run_ids must not be empty")

    # Ensure output directory exists
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    print_flush(f"Loading VALID_BEST validation runs for {len(calibration_run_ids)} calibration_run_ids...")

    # 1) Retrieve all VALID_BEST ValidationRuns for the given calibration_run_ids
    validation_runs_qs = (
        ValidationRun.objects
        .select_related('calibration_run', 'calibration_run__gage', 'calibration_run__optimization')
        .filter(calibration_run_id__in=calibration_run_ids,
                validation_type=ValidationType.VALID_BEST.value)
    )

    runs_by_calibration_run_id: dict[int, ValidationRun] = {}
    base_info_by_calibration_run_id: dict[int, tuple[int, str, str]] = {}  # calibration_run_id -> (validation_run_id, gage_id, formulation)
    missing_calibration_run_ids = set(calibration_run_ids)

    for validation_run in validation_runs_qs:
        calibration_run = validation_run.calibration_run
        runs_by_calibration_run_id[calibration_run.id] = validation_run
        missing_calibration_run_ids.discard(calibration_run.id)
        gage_id = calibration_run.gage.gage_id if calibration_run.gage else ""
        formulation = calibration_run.user_formulation_name or (
            calibration_run.optimization.name if calibration_run.optimization else ""
        )
        base_info_by_calibration_run_id[calibration_run.id] = (validation_run.id, gage_id, formulation)

    # Warn if any requested calibration_run_id has no VALID_BEST ValidationRun
    for calibration_run_id in sorted(missing_calibration_run_ids):
        print_flush(f"WARNING: No VALID_BEST ValidationRun found for calibration_run_id={calibration_run_id}")

    if not runs_by_calibration_run_id:
        raise CommandError("No VALID_BEST ValidationRuns found for any requested calibration_run_id.")

    # 2) Retrieve all ValidationMetrics for the collected ValidationRuns
    validation_metrics_qs = (
        ValidationMetrics.objects
        .filter(validation_run__in=runs_by_calibration_run_id.values())
        .select_related('metric', 'validation_run')
        .only('period', 'metric_value', 'metric__name', 'validation_run')
        .order_by('validation_run__calibration_run_id', 'period', 'metric__name')
    )

    # 3) Build a mapping of (calibration_run_id, period) -> {metric_name: value}
    #    and collect the union of all metric names across runs
    metric_names: set[str] = set()
    rows_map: dict[tuple[int, str], dict[str, float]] = {}

    for validation_metric in validation_metrics_qs:
        calibration_run_id = validation_metric.validation_run.calibration_run_id
        key = (calibration_run_id, validation_metric.period)
        bucket = rows_map.setdefault(key, {})
        metric_names.add(validation_metric.metric.name)
        bucket[validation_metric.metric.name] = validation_metric.metric_value

    # 4) Prepare the CSV header (union of metric columns sorted for consistency)
    metric_cols = sorted(metric_names)
    fieldnames = [
        'calibration_run_id',
        'validation_run_id',
        'gage_id',
        'formulation',
        'evalPeriod'
    ] + metric_cols

    # 5) Write all collected rows to the CSV
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Sort by calibration_run_id then period for stable output
        for (calibration_run_id, period) in sorted(rows_map.keys(), key=lambda x: (x[0], x[1])):
            validation_run_id, gage_id, formulation = base_info_by_calibration_run_id.get(
                calibration_run_id, ("", "", "")
            )
            metrics_map = rows_map[(calibration_run_id, period)]
            row = {
                'calibration_run_id': calibration_run_id,
                'validation_run_id': validation_run_id,
                'gage_id': gage_id,
                'formulation': formulation,
                'evalPeriod': period,
            }
            for metric_name in metric_cols:
                row[metric_name] = metrics_map.get(metric_name, "")
            writer.writerow(row)

    print_flush(f"Wrote {len(rows_map)} rows to {out_path} with {len(metric_cols)} metric columns.")


def export_validation_parameters_csv(calibration_run_ids: list[int], out_path: str) -> None:
    """
    Export a CSV of 'best' calibration parameters for the given calibration_run_ids.

    Columns:
      calibration_run_id, validation_run_id, gage_id, formulation, best_iteration, <param_1>, <param_2>, ...
    One row per calibration_run_id. Parameter columns are the union across all runs.

    Selection rule:
      Use the Iteration with best_params=True for each calibration run.
    """
    if not calibration_run_ids:
        raise ValueError("calibration_run_ids must not be empty")

    # Ensure output directory exists
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    print_flush(f"Loading best parameters for {len(calibration_run_ids)} calibration_run_ids...")

    # Map: calibration_run_id -> VALID_BEST validation_run_id (for column #2)
    validation_runs_qs = (
        ValidationRun.objects
        .filter(calibration_run_id__in=calibration_run_ids, validation_type=ValidationType.VALID_BEST.value)
        .only('id', 'calibration_run_id')
    )
    validation_run_id_by_calibration_run_id: dict[int, int] = {
        vr.calibration_run_id: vr.id for vr in validation_runs_qs
    }
    for calibration_run_id in sorted(set(calibration_run_ids) - set(validation_run_id_by_calibration_run_id.keys())):
        print_flush(f"WARNING: No VALID_BEST ValidationRun found for calibration_run_id={calibration_run_id}")

    # Pull best iterations (best_params=True) and prefetch parameters for names/values
    best_iterations_qs = (
        Iteration.objects
        .select_related('calibration_run', 'calibration_run__gage', 'calibration_run__optimization')
        .filter(calibration_run_id__in=calibration_run_ids, best_params=True)
        .prefetch_related('iterationparameter_set__calibration_parameter')
        .order_by('calibration_run_id', 'iteration_num')
    )

    # Build a map: calibration_run_id -> list of best iterations (should be exactly 1)
    best_by_calibration_run_id: dict[int, list[Iteration]] = {}
    for iteration in best_iterations_qs:
        best_by_calibration_run_id.setdefault(iteration.calibration_run_id, []).append(iteration)

    # Warn on missing or multiple bests; choose the first deterministically if multiple
    rows: list[dict[str, object]] = []
    parameter_names: set[str] = set()

    requested_set = set(calibration_run_ids)
    found_set = set(best_by_calibration_run_id.keys())
    for missing_id in sorted(requested_set - found_set):
        print_flush(f"WARNING: No best iteration (best_params=True) for calibration_run_id={missing_id}")

    for calibration_run_id in sorted(found_set):
        best_list = best_by_calibration_run_id[calibration_run_id]
        if len(best_list) > 1:
            print_flush(
                f"WARNING: Multiple best iterations for calibration_run_id={calibration_run_id}; "
                f"using the first (iteration_num={best_list[0].iteration_num})"
            )

        best_iteration = best_list[0]
        calibration_run = best_iteration.calibration_run
        gage_id = calibration_run.gage.gage_id if calibration_run.gage else ""
        formulation = calibration_run.user_formulation_name or (
            calibration_run.optimization.name if calibration_run.optimization else ""
        )
        validation_run_id = validation_run_id_by_calibration_run_id.get(calibration_run_id, "")

        # Collect parameter name -> tuned_value for this best iteration
        param_map: dict[str, float | None] = {}
        for ip in best_iteration.iterationparameter_set.all():
            name = ip.calibration_parameter.name
            parameter_names.add(name)
            param_map[name] = ip.tuned_value

        rows.append({
            "calibration_run_id": calibration_run_id,
            "validation_run_id": validation_run_id,
            "gage_id": gage_id,
            "formulation": formulation,
            "best_iteration": best_iteration.iteration_num,
            "_params": param_map,  # expanded at write time
        })

    if not rows:
        raise CommandError("No best parameters found for any requested calibration_run_id.")

    # Write CSV with union of parameter columns (sorted for stable schema)
    param_cols = sorted(parameter_names)
    fieldnames = [
        "calibration_run_id",
        "validation_run_id",       # <-- 2nd column
        "gage_id",
        "formulation",
        "best_iteration",
    ] + param_cols

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out_row = {
                "calibration_run_id": row["calibration_run_id"],
                "validation_run_id": row["validation_run_id"],
                "gage_id": row["gage_id"],
                "formulation": row["formulation"],
                "best_iteration": row["best_iteration"],
            }
            params = row["_params"]  # type: ignore[assignment]
            for name in param_cols:
                out_row[name] = params.get(name, "")  # blank if missing in this run
            writer.writerow(out_row)

    print_flush(f"Wrote {len(rows)} rows to {out_path} with {len(param_cols)} parameter columns.")




class Command(BaseCommand):
    help = 'Export VALID_BEST validation metrics and best-parameter CSVs for multiple CalibrationRun IDs.'

    def add_arguments(self, parser):
        parser.add_argument(
            'calibration_run_ids',
            nargs='+',
            type=int,
            help='One or more calibration_run_id values (space-separated).'
        )
        # Backward-compatible alias: --out acts like --out-dir
        parser.add_argument(
            '--out', '--out-dir',
            dest='out_dir',
            type=str,
            default=None,
            help='Directory to write CSV files (default: current directory).'
        )
        parser.add_argument(
            '--metrics-out',
            dest='metrics_out_path',
            type=str,
            default=None,
            help='Full path for the metrics CSV. Overrides --out-dir if set.'
        )
        parser.add_argument(
            '--params-out',
            dest='params_out_path',
            type=str,
            default=None,
            help='Full path for the parameters CSV. Overrides --out-dir if set.'
        )

    def handle(self, *args, **options):
        calibration_run_ids = options['calibration_run_ids']
        out_dir = options.get('out_dir')
        metrics_out_path = options.get('metrics_out_path')
        params_out_path = options.get('params_out_path')

        # Resolve defaults
        if not metrics_out_path:
            base_dir = out_dir or os.getcwd()
            metrics_out_path = os.path.join(base_dir, 'regionalization_metrics.csv')
        if not params_out_path:
            base_dir = out_dir or os.getcwd()
            params_out_path = os.path.join(base_dir, 'regionalization_parameters.csv')

        # Ensure parent dirs exist (exporters also guard, but this gives early failure if needed)
        for p in (metrics_out_path, params_out_path):
            d = os.path.dirname(p)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)

        print_flush(f"Metrics CSV → {metrics_out_path}")
        print_flush(f"Parameters CSV → {params_out_path}")

        export_validation_metrics_csv(calibration_run_ids, metrics_out_path)
        export_validation_parameters_csv(calibration_run_ids, params_out_path)
