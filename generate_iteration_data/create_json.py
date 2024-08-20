import json


def generate_calibration_data(worker_names, iterations_per_worker, calibration_run_id):
    data = []

    for worker in worker_names:
        for iteration in range(iterations_per_worker):
            entry = {
                "calibration_run_id": calibration_run_id,
                "iteration": iteration,
                "worker_name": worker
            }
            data.append(entry)

    return data


def save_data_to_file(data, file_name):
    with open(file_name, 'w') as f:
        f.write('[\n')
        for i, entry in enumerate(data):
            json.dump(entry, f)
            if i < len(data) -1:
                f.write(',')  # command after each object except the last one
            f.write('\n')
        f.write(']\n')
    print(f"Data has been saved to {file_name}")


if __name__ == "__main__":
    # Example input
    worker_names = [
        "ngen_riwvw4t0_worker",

    ]
    iterations_per_worker = 21
    calibration_run_id = 96

    # Generate the data
    data = generate_calibration_data(worker_names, iterations_per_worker, calibration_run_id)

    # Save the data to a file
    save_data_to_file(data, "kge_dds_report_iteration.json")
