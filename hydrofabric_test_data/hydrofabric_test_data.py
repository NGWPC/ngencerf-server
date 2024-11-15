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
            "module_name": "SFT",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/SFT/2024_Nov_14_14_16_54"
            },
            "calibrate_parameters": [
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.5062880754266784",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters/meters [m/m]"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.012038240828663583",
                    "description": "saturated capillary head",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " meters [m]"
                },
                {
                    "name": "soil_params.b",
                    "initial_value": "4.605729579925537",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": " "
                }
            ],
            "output_variables": [
                {
                    "variable": "ACTUAL_ET",
                    "description": "AET"
                },
                {
                    "variable": "DEEP_GW_TO_CHANNEL_FLUX",
                    "description": "deep_gw_to_channel_flux"
                },
                {
                    "variable": "DIRECT_RUNOFF",
                    "description": "direct_runoff"
                },
                {
                    "variable": "GIUH_RUNOFF",
                    "description": "giuh_runoff"
                },
                {
                    "variable": "NASH_LATERAL_RUNOFF",
                    "description": "nash_lateral_runoff"
                },
                {
                    "variable": "POTENTIAL_ET",
                    "description": "PET"
                },
                {
                    "variable": "Q_OUT",
                    "description": "q_out"
                },
                {
                    "variable": "RAIN_RATE",
                    "description": "rain_rate"
                },
                {
                    "variable": "SOIL_STORAGE",
                    "description": "soil_storage"
                },
                {
                    "variable": "TG",
                    "description": "ground_temperature"
                },
                {
                    "variable": "ice_fraction_schaake",
                    "description": "ice_fraction_schaake flag"
                },
                {
                    "variable": "soil_ice_fraction",
                    "description": "soil_ice_fraction"
                },
                {
                    "variable": "soil_moisture_fraction",
                    "description": "soil_moisture_fraction"
                }
            ]
        },

        {
            "module_name": "Sac-SMA",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01123000/PARAMS/USGS/Sac-SMA/2024_Nov_14_15_58_57"
            },
            "calibrate_parameters": [
                {
                    "name": "uztwm",
                    "initial_value": "53.633659362793",
                    "description": "upper zone tension water maximum storage",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "uzfwm",
                    "initial_value": "49.4127578735352",
                    "description": "Maximum upper zone free water",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lztwm",
                    "initial_value": "167.917007446289",
                    "description": "Maximum lower zone tension water",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lzfsm",
                    "initial_value": "12.5138731002808",
                    "description": "Maximum lower zone free water, secondary (aka supplemental)",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lzfpm",
                    "initial_value": "179.637054443359",
                    "description": "Maximum lower zone free water, primary",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "adimp",
                    "initial_value": "0.0",
                    "description": "Additional impervious area due to saturation",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "uzk",
                    "initial_value": "0.504685878753662",
                    "description": "Upper zone recession coefficient",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "per day "
                },
                {
                    "name": "lzpk",
                    "initial_value": "0.0421152859926224",
                    "description": "Lower zone recession coefficient, primary",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "lzsk",
                    "initial_value": "0.177162826061249",
                    "description": "Lower zone recession coefficient, secondary (aka supplemental)",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "zperc",
                    "initial_value": "46.9980163574219",
                    "description": "Minimum percolation rate coefficient",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "rexp",
                    "initial_value": "1.38430523872375",
                    "description": "Percolation equation exponent",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "pctim",
                    "initial_value": "0.0",
                    "description": "impervious  fraction of the watershed area ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "pfree",
                    "initial_value": "0.0709966793656349",
                    "description": "fraction of water percolating from upper zone directly to lower zone free water storage. ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "riva",
                    "initial_value": "0.0",
                    "description": "Percent of the basin that is riparian area",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "decimal percent"
                }
            ],
            "output_variables": [
                {
                    "variable": "baseflow non-channel component ",
                    "description": "baseflow non-channel component "
                },
                {
                    "variable": "bfp",
                    "description": "channel baseflow component "
                },
                {
                    "variable": "bfs",
                    "description": "channel baseflow component"
                },
                {
                    "variable": "eta",
                    "description": "actual evapotranspiration"
                },
                {
                    "variable": "qg",
                    "description": "baseflow"
                },
                {
                    "variable": "qs",
                    "description": "surface runoff from all sources."
                },
                {
                    "variable": "roimp",
                    "description": "impervious area runoff"
                },
                {
                    "variable": "sdro",
                    "description": "direct runoff"
                },
                {
                    "variable": "sif",
                    "description": "interflow"
                },
                {
                    "variable": "ssur",
                    "description": "surface runoff "
                },
                {
                    "variable": "tci",
                    "description": "total channel inflow"
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
