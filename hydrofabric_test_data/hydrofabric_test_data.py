geopackage_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/camels1/gauge_01123000.gpkg",
}

forcing_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/aorc_nwm/csv_basin_group1/Gage_01123000/"
}

observational_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/streamflow_obs/01123000_hourly_discharge.csv"
}

hydrofabric_module_metadata_real_data = {
    "modules": [
        {
            "module_name": "CFE-S",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/CFE-S/2024_Oct_22_19_37_04"
            },
            "calibrate_parameters": [
                {
                    "name": "soil_params.b",
                    "initial_value": "7.55060482025146",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "soil_params.satdk",
                    "initial_value": "5.80674532102421e-06",
                    "description": "saturated hydraulic conductivity",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/second [m s-1]"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.141000002622604",
                    "description": "saturated capillary head",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters [m]"
                },
                {
                    "name": "soil_params.slop",
                    "initial_value": "0.155113384127617",
                    "description": "this factor (0-1) modifies the gradient of the hydraulic head at the soil bottom.  0=no-flow.",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/meters [m/m]state"
                },
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.401015371084213",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/meters [m/m]"
                },
                {
                    "name": "max_gw_storage",
                    "initial_value": "0.248876617431641",
                    "description": "maximum storage in the conceptual reservoir",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters [m]"
                },
                {
                    "name": "Cgw",
                    "initial_value": "0.00499999988824129",
                    "description": "the primary outlet coefficient",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/hour [m h-1]"
                },
                {
                    "name": "expon",
                    "initial_value": "3.62192964553833",
                    "description": "exponent parameter (1.0 for linear reservoir)",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "K_lf",
                    "initial_value": "0.1",
                    "description": "Nash Config param - primary reservoir",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                }
            ],
            "output_variables": [
                {
                    "variable": "ACTUAL_ET",
                    "description": None
                },
                {
                    "variable": "DEEP_GW_TO_CHANNEL_FLUX",
                    "description": None
                },
                {
                    "variable": "DIRECT_RUNOFF",
                    "description": None
                },
                {
                    "variable": "GIUH_RUNOFF",
                    "description": None
                },
                {
                    "variable": "GW_STORAGE",
                    "description": None
                },
                {
                    "variable": "INFILTRATION_EXCESS",
                    "description": None
                },
                {
                    "variable": "NASH_LATERAL_RUNOFF",
                    "description": None
                },
                {
                    "variable": "POTENTIAL_ET",
                    "description": None
                },
                {
                    "variable": "Q_OUT",
                    "description": None
                },
                {
                    "variable": "RAIN_RATE",
                    "description": None
                },
                {
                    "variable": "SOIL_STORAGE",
                    "description": None
                },
                {
                    "variable": "SOIL_STORAGE_CHANGE",
                    "description": None
                },
                {
                    "variable": "SOIL_TO_GW_FLUX",
                    "description": None
                },
                {
                    "variable": "SURF_RUNOFF_SCHEME",
                    "description": None
                }
            ]
        },

        {
            "module_name": "CFE-X",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/CFE-X/2024_Oct_24_21_17_26"
            },
            "calibrate_parameters": [
                {
                    "name": "a_Xinanjiang_inflection_point_parameter",
                    "initial_value": "-0.227584883570671",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "b_Xinanjiang_shape_parameter",
                    "initial_value": "0.710917413234711",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "x_Xinanjiang_shape_parameter",
                    "initial_value": "0.0215666070580482",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "soil_params.b",
                    "initial_value": "7.58413219451904",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "soil_params.satdk",
                    "initial_value": "7.94075094745494e-06",
                    "description": "saturated hydraulic conductivity",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/second [m s-1]"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.141000017523766",
                    "description": "saturated capillary head",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters [m]"
                },
                {
                    "name": "soil_params.slop",
                    "initial_value": "0.150730654597282",
                    "description": "this factor (0-1) modifies the gradient of the hydraulic head at the soil bottom.  0=no-flow.",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/meters [m/m]state"
                },
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.403563052415848",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/meters [m/m]"
                },
                {
                    "name": "max_gw_storage",
                    "initial_value": "0.248876617431641",
                    "description": "maximum storage in the conceptual reservoir",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters [m]"
                },
                {
                    "name": "Cgw",
                    "initial_value": "0.00499999988824129",
                    "description": "the primary outlet coefficient",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/hour [m h-1]"
                },
                {
                    "name": "expon",
                    "initial_value": "3.62192964553833",
                    "description": "exponent parameter (1.0 for linear reservoir)",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                },
                {
                    "name": "K_lf",
                    "initial_value": "0.1",
                    "description": "Nash Config param - primary reservoir",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                }
            ],
            "output_variables": [
                {
                    "variable": "ACTUAL_ET",
                    "description": None
                },
                {
                    "variable": "DEEP_GW_TO_CHANNEL_FLUX",
                    "description": None
                },
                {
                    "variable": "DIRECT_RUNOFF",
                    "description": None
                },
                {
                    "variable": "GIUH_RUNOFF",
                    "description": None
                },
                {
                    "variable": "GW_STORAGE",
                    "description": None
                },
                {
                    "variable": "INFILTRATION_EXCESS",
                    "description": None
                },
                {
                    "variable": "NASH_LATERAL_RUNOFF",
                    "description": None
                },
                {
                    "variable": "POTENTIAL_ET",
                    "description": None
                },
                {
                    "variable": "Q_OUT",
                    "description": None
                },
                {
                    "variable": "RAIN_RATE",
                    "description": None
                },
                {
                    "variable": "SOIL_STORAGE",
                    "description": None
                },
                {
                    "variable": "SOIL_STORAGE_CHANGE",
                    "description": None
                },
                {
                    "variable": "SOIL_TO_GW_FLUX",
                    "description": None
                },
                {
                    "variable": "SURF_RUNOFF_SCHEME",
                    "description": None
                }
            ]
        },

        {
            "module_name": "Noah-OWP-Modular",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/Noah-OWP-Modular/2024_Oct_22_13_15_07"
            },
            "calibrate_parameters": [
                {
                    "name": "MFSNO",
                    "initial_value": 2.5,
                    "description": "snowmelt curve parameter",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "CWPVT",
                    "initial_value": 0.67,
                    "description": "empirical canopy wind parameter",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "VCMX25",
                    "initial_value": 60.0,
                    "description": "maximum rate of carboxylation at 25c",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "umol co2/m**2/s"
                },
                {
                    "name": "MP",
                    "initial_value": 9.0,
                    "description": "slope of conductance-to-photosynthesis relationship",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "RSURF_SNOW",
                    "initial_value": 50.0,
                    "description": "surface resistence for snow [s/m]",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "s/m"
                },
                {
                    "name": "RSURF_EXP",
                    "initial_value": 5.0,
                    "description": "exponent in the shape parameter for soil resistance option 1",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "ETRAN",
                    "description": "transpiration rate (mm/s)"
                },
                {
                    "variable": "EVAPOTRANS",
                    "description": "evapotranspiration rate (m/s)"
                },
                {
                    "variable": "QINSUR",
                    "description": "total liquid water input to surface rate (m/s)"
                },
                {
                    "variable": "QSEVA",
                    "description": "evaporation rate (m/s)"
                },
                {
                    "variable": "SNEQV",
                    "description": "snow water equivalent (mm)"
                },
                {
                    "variable": "TG",
                    "description": "surface/ground temperature (becomes snow surface temperature when snow is present)"
                },
                {
                    "variable": "TGS",
                    "description": "ground temperature (K) (is equal to TG when no snow and equal to bottom snow element temperature when there is snow)"
                }
            ]
        },

        {
            "module_name": "T-Route",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/T-Route/2024_Oct_22_13_15_08"
            },
            "calibrate_parameters": [],
            "output_variables": [
                {
                    "variable": "channel_exit_water_x-section__volume_flow_rate",
                    "description": None
                },
                {
                    "variable": "channel_water__mean_depth",
                    "description": None
                },
                {
                    "variable": "channel_water_flow__speed",
                    "description": None
                },
                {
                    "variable": "lake_surface__elevation",
                    "description": None
                },
                {
                    "variable": "lake_water~incoming__volume_flow_rate",
                    "description": None
                },
                {
                    "variable": "lake_water~outgoing__volume_flow_rate",
                    "description": None
                }
            ]
        }
    ]
}
