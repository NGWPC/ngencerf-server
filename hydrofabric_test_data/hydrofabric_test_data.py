geopackage_sample_data = {
    "url": "s3://ngwpc-dev/Yuqiong.Liu/data/camels1/gauge_01123000.gpkg",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

forcing_sample_data = {
    "url": "s3://ngwpc-dev/Yuqiong.Liu/data/aorc_nwm/csv_basin_group1/Gage_01123000/"
}

observational_sample_data = {
    "url": "s3://ngwpc-dev/Yuqiong.Liu/data/streamflow_obs/01123000_hourly_discharge.csv"
}

# For testing
module_metadata_sample_data = {"modules": [
    {
        "module_name": "Noah-OWP-Modular",
        "module_output_variables": [
            {
                "name": "QINSUR",
                "description": "description of variable",
            },
            {
                "name": "ETRAN",
                "description": "description of variable",
            },
            {
                "name": "QSEVA",
                "description": "description of variable",
            },
        ],
        "module_parameters": [
            {
                "name": "parameter1",
                "data_type": "double",
                "description": "description of variable",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            },

            {
                "name": "parameter2",
                "data_type": "double",
                "description": "description of variable",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            },
            {
                "name": "parameter3",
                "data_type": "double",
                "description": "description of variable",
                # "units": "m/s",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            }

        ]
    },
]
}

hydrofabric_module_metadata_real_data = {"modules": [
    {
        "module_name": "CFE-S",
        "parameter_file": {
            "url": "s3://ngwpc-dev/DanielCumpton/Gage_6719505/CFE-X"
        },
        "calibrate_parameters": [
            {
                "name": "soil_params.b",
                "initial_value": "5.3179178237915",
                "description": "param b",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.satdk",
                "initial_value": "3.1252143344318e-06",
                "description": "param satdk",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.satpsi",
                "initial_value": "",
                "description": "param satpsi",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.slop",
                "initial_value": "",
                "description": "param slop",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.smcmax",
                "initial_value": "",
                "description": "param smcmax",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "Cgw",
                "initial_value": "0.00499999988824129",
                "description": "Cgw",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "expon",
                "initial_value": "3.94163870811462",
                "description": "expon",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "K_lf",
                "initial_value": "0.1",
                "description": "K_lf",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            }
        ],
        "module_output_variables": [
            {
                "name": "outputVariable1",
                "description": "decsription for var 1"
            },
            {
                "name": "outputVariable2",
                "description": "decsription for var 2"
            }
        ]
    },
    {
        "module_name": "CFE-X",
        "parameter_file": {
            "url": "s3://ngwpc-dev/DanielCumpton/Gage_6719505/CFE-X"
        },
        "calibrate_parameters": [
            {
                "name": "soil_params.b",
                "initial_value": "5.3179178237915",
                "description": "param b",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.satdk",
                "initial_value": "3.1252143344318e-06",
                "description": "param satdk",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.satpsi",
                "initial_value": "",
                "description": "param satpsi",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.slop",
                "initial_value": "",
                "description": "param slop",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "soil_params.smcmax",
                "initial_value": "",
                "description": "param smcmax",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "Cgw",
                "initial_value": "0.00499999988824129",
                "description": "Cgw",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "expon",
                "initial_value": "3.94163870811462",
                "description": "expon",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "K_lf",
                "initial_value": "0.1",
                "description": "K_lf",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "a_Xinanjiang_inflection_point_parameter",
                "initial_value": "-0.147509053349495",
                "description": "K_lf",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "b_Xinanjiang_shape_parameter_set",
                "initial_value": "",
                "description": "K_lf",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            },
            {
                "name": "x_Xinanjiang_shape_parameter",
                "initial_value": "0.444413632154465",
                "description": "K_lf",
                "min": "0",
                "max": "100",
                "data_type": "double",
                "units": "meters/second [m s-1]",
                "calibratable": "true"
            }
        ],
        "module_output_variables": [
            {
                "name": "outputVariable1",
                "description": "decsription for var 1"
            },
            {
                "name": "outputVariable2",
                "description": "decsription for var 2"
            }
        ]
    },
    {
        "module_name": "Noah-OWP-Modular",
        "parameter_file": {
            "url": "s3://ngwpc-hydrofabric/01123000/NOAH-OWP-Modular"
        },
        "calibrate_parameters": [
            {
                "name": "MFSNO",
                "initial_value": 2.5,
                "description": "snowmelt curve parameter",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": None,
                "calibratable": True,
            },
            {
                "name": "CWPVT",
                "initial_value": 0.67,
                "description": "empirical canopy wind parameter",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": None,
                "calibratable": True,
            },
            {
                "name": "VCMX25",
                "initial_value": 60.0,
                "description": "maximum rate of carboxylation at 25c",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": "umol co2/m**2/s",
                "calibratable": True,
            },
            {
                "name": "MP",
                "initial_value": 9.0,
                "description": "slope of conductance-to-photosynthesis relationship",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": None,
                "calibratable": True,
            },
            {
                "name": "RSURF_SNOW",
                "initial_value": 50.0,
                "description": "surface resistence for snow [s/m]",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": "s/m",
                "calibratable": True,
            },
            {
                "name": "RSURF_EXP",
                "initial_value": 5.0,
                "description": "exponent in the shape parameter for soil resistance option 1",
                "min": None,
                "max": None,
                "data_type": "double",
                "units": None,
                "calibratable": True,
            }
        ],
        "module_output_variables": [
            {
                "name": "ETRAN",
                "description": "transpiration rate (mm/s)"
            },
            {
                "name": "EVAPOTRANS",
                "description": "evapotranspiration rate (m/s)"
            },
            {
                "name": "QINSUR",
                "description": "total liquid water input to surface rate (m/s)"
            },
            {
                "name": "QSEVA",
                "description": "evaporation rate (m/s)"
            },
            {
                "name": "SNEQV",
                "description": "snow water equivalent (mm)"
            },
            {
                "name": "TG",
                "description": "surface/ground temperature (becomes snow surface temperature when snow is present)"
            },
            {
                "name": "TGS",
                "description": "ground temperature (K) (is equal to TG when no snow and equal to bottom snow element temperature when there is snow)"
            }
        ]
    },
    {
        "module_name": "T-Route",
        "parameter_file": {
            "url": "s3://ngwpc-hydrofabric/01123000/NOAH-OWP-Modular"
        },
        "calibrate_parameters": [

        ],
        "module_output_variables": [
            {
                "name": "ETRAN",
                "description": "transpiration rate (mm/s)"
            }
        ]
    }
]
}

# For testing
module_sample_data = {"modules": [
    {
        "module_name": "Noah-OWP-Modular",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ],
    },
    {
        "module_name": "Snow-17",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "module_name": "UEB",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "module_name": "CFE-S",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "module_name": "CFE-X",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "module_name": "PET",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Evapotranspiration"
        ]
    },
    {
        "module_name": "TopModel",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "Sac-SMA",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "LASAM",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "SMP",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "module_name": "SFT",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "module_name": "T-Route",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Routing"
        ],
    },
    {
        "module_name": "SCHISM",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    },
    {
        "module_name": "SFINCS",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    },
    # {
    #     "module_name": "Topoflow",
    #     "description": "description of module",
    #     "module_version": {
    #         "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
    #         "version_url": "https://www.acme-corp.com",
    #         "version_date": "2024-08-29T09:12:33.001Z"
    #     },
    #     "groups": [
    #         "Glacier"
    #     ]
    # }
]
}
