
geopackage_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/camels1/gauge_01123000.gpkg",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

forcing_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/aorc_nwm/csv_basin_group1/Gage_01123000/"
}

observational_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/streamflow_obs/01123000_hourly_discharge.csv"
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
{
        "module_name": "Topoflow",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    }
]
}

