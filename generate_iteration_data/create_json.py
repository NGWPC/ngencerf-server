import json


def generate_calibration_data(worker_names, iteration_range_per_worker, calibration_run_id, optimization):  # noqa : F811
    data = {'optimization': optimization}
    list = []
    data['list'] = list

    for worker in worker_names:
        for iteration in iteration_range_per_worker:
            entry = {
                "calibration_run_id": calibration_run_id,
                "iteration": iteration,
                "worker_name": worker
            }
            list.append(entry)

    return data


def save_data_to_file(data, file_name):
    with open(file_name, 'w') as f:
        f.write('{\n')
        f.write(f'  "optimization": "{data["optimization"]}",\n')
        f.write('  "list": [\n')
        for i, entry in enumerate(data['list']):
            f.write('     ')
            json.dump(entry, f)
            if i < len(data['list']) - 1:
                f.write(',\n')  # Add a comma after each object except the last one
            else:
                f.write('\n')  # No comma for the last item
        f.write('  ]\n')
        f.write('}\n')
    print(f"Data has been saved to {file_name}")


if __name__ == "__main__":
    dds_worker_names = [
        "ngen_riwvw4t0_worker",

    ]
    gwo_worker_names = [
        "ngen_2hhxgvfp_worker", "ngen_7ut6v8cz_worker", "ngen_ci4lynry_worker", "ngen_irn0uy_c_worker",
        "ngen_ppih7w1h_worker", "ngen_2s51akwe_worker", "ngen_912z93re_worker", "ngen_cuph8gcn_worker",
        "ngen_lp4ve_wv_worker", "ngen_w4vw2knc_worker", "ngen__5qjqrr0_worker", "ngen_aooy701l_worker",
        "ngen_g1cpyeee_worker", "ngen_mukrse7k_worker", "ngen_x3sb5383_worker", "ngen_6ejzryvv_worker",
        "ngen_ch2p7j4r_worker", "ngen_iidhk_ub_worker", "ngen_p_gj6utp_worker", "ngen_yyhb9nnw_worker"
    ]

    pso_worker_names = [
        "ngen_02nzo_ff_worker", "ngen_5xt0t45s_worker", "ngen_973t7qip_worker", "ngen_didiij2u_worker", "ngen_oulhhd5l_worker",
        "ngen_0aan9y2e_worker", "ngen_7nx9vlwb_worker", "ngen_9q_nsck__worker", "ngen_i6644nt8_worker", "ngen_q11zhh6y_worker",
        "ngen_0q741zk8_worker", "ngen___86h8fw_worker", "ngen_app2nsy8_worker", "ngen_kg_i92u2_worker", "ngen_w1554g9c_worker",
        "ngen_570t0alv_worker", "ngen_8tyw3pbd_worker", "ngen_b5ajre08_worker", "ngen_m561oqmp_worker", "ngen_y_10329w_worker",

    ]
    # DDS counts iterations from 0
    # GWO and PSO count from 1

    optimization = 'gwo'
    worker_names = None

    # Note that ending range is n+1
    if optimization == 'dds':
        iteration_range_per_worker = range(0, 501)
        worker_names = dds_worker_names
    elif optimization == 'gwo':
        iteration_range_per_worker = range(1, 27)
        worker_names = gwo_worker_names
    else:
        iteration_range_per_worker = range(1, 52)
        worker = pso_worker_names

    calibration_run_id = 107

    # Generate the data
    data = generate_calibration_data(worker_names, iteration_range_per_worker, calibration_run_id, optimization)

    # Save the data to a file
    save_data_to_file(data, f"kge_{optimization}_report_iteration.json")
