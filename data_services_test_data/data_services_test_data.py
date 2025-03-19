geopackage_sample_data = {
    "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/GEOPACKAGE/USGS/2025_Jan_17_21_01_40/gauge_01123000.gpkg"
}

observational_sample_data = {
    "uri": "s3://ngwpc-hydrofabric/2.1/CONUS/01011000/OBSERVATIONAL/USGS/2024_Sep_18_10_05_59/01011000_hourly_discharge.csv"
}

eds_module_metadata_real_data = {
    "modules": [
        {
            "module_name": "CFE-X",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/CFE-X/2025_Feb_06_20_25_47"
            },
            "calibrate_parameters": [
                {
                    "name": "a_Xinanjiang_inflection_point_parameter",
                    "initial_value": "-0.22757151722908[]",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "b_Xinanjiang_shape_parameter",
                    "initial_value": "0.710872650146484[]",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "x_Xinanjiang_shape_parameter",
                    "initial_value": "0.0215711779892445[]",
                    "description": "when surface_water_partitioning_scheme=Xinanjiang ",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "soil_params.b",
                    "initial_value": "7.551834583282471[]",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": "2",
                    "max": "15",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "soil_params.satdk",
                    "initial_value": "1.2793798091406582e-06[m s-1]",
                    "description": "saturated hydraulic conductivity",
                    "min": "0.0000001",
                    "max": "0.000726",
                    "data_type": "double",
                    "units": "m s-1"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.020759036123258832[m]",
                    "description": "saturated capillary head",
                    "min": "0.03",
                    "max": "0.955",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "soil_params.slop",
                    "initial_value": "0.15070995688438416[m/m]",
                    "description": "this factor (0-1) modifies the gradient of the hydraulic head at the soil bottom.  0=no-flow.",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.40357479453086853[m/m]",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "soil_params.wltsmc",
                    "initial_value": "0.04700000211596489[m/m]",
                    "description": "wilting point soil moisture content",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "max_gw_storage",
                    "initial_value": "0.24881846999999999[m]",
                    "description": "maximum storage in the conceptual reservoir",
                    "min": "0.01",
                    "max": "0.25",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "Cgw",
                    "initial_value": "0.005[m h-1]",
                    "description": "the primary outlet coefficient",
                    "min": "0.0000018",
                    "max": "0.0018",
                    "data_type": "double",
                    "units": "m h-1"
                },
                {
                    "name": "expon",
                    "initial_value": "3.0[]",
                    "description": "exponent parameter (1.0 for linear reservoir)",
                    "min": "1",
                    "max": "8",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "K_lf",
                    "initial_value": "0.1[]",
                    "description": "Nash Config param - primary reservoir",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "refkdt",
                    "initial_value": "2.0[]",
                    "description": "Parameter in the surface runoff parameterization",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "ACTUAL_ET",
                    "description": "Actual ET"
                },
                {
                    "variable": "DEEP_GW_TO_CHANNEL_FLUX",
                    "description": "Groundwater recharge rate to channel "
                },
                {
                    "variable": "DIRECT_RUNOFF",
                    "description": "Surface runoff"
                },
                {
                    "variable": "GIUH_RUNOFF",
                    "description": "Runoff for GIUH routing"
                },
                {
                    "variable": "GW_STORAGE",
                    "description": "Groundwater storage"
                },
                {
                    "variable": "INFILTRATION_EXCESS",
                    "description": "Excess infiltration"
                },
                {
                    "variable": "NASH_LATERAL_RUNOFF",
                    "description": "Lateral runoff"
                },
                {
                    "variable": "NWM_PONDED_DEPTH",
                    "description": "Ponded water depth \t"
                },
                {
                    "variable": "POTENTIAL_ET",
                    "description": "Potential ET"
                },
                {
                    "variable": "Q_OUT",
                    "description": "Streamflow output"
                },
                {
                    "variable": "RAIN_RATE",
                    "description": "Precipitation rate"
                },
                {
                    "variable": "SOIL_STORAGE",
                    "description": "Soil water storage"
                },
                {
                    "variable": "SOIL_STORAGE_CHANGE",
                    "description": "Changes in soil water storage"
                },
                {
                    "variable": "SOIL_TO_GW_FLUX",
                    "description": "Soil to groundwater recharge rate"
                },
                {
                    "variable": "SURF_RUNOFF_SCHEME",
                    "description": "Surface runoff scheme"
                }
            ]
        },
        {
            "module_name": "CFE-S",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/CFE-S/2025_Feb_06_18_02_59"
            },
            "calibrate_parameters": [
                {
                    "name": "soil_params.b",
                    "initial_value": "7.551834583282471[]",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": "2",
                    "max": "15",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "soil_params.satdk",
                    "initial_value": "1.1083597711476886e-06[m s-1]",
                    "description": "saturated hydraulic conductivity",
                    "min": "0.0000001",
                    "max": "0.000726",
                    "data_type": "double",
                    "units": "m s-1"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.027170022789296738[m]",
                    "description": "saturated capillary head",
                    "min": "0.03",
                    "max": "0.955",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "soil_params.slop",
                    "initial_value": "0.15539392828941345[m/m]",
                    "description": "this factor (0-1) modifies the gradient of the hydraulic head at the soil bottom.  0=no-flow.",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.4009084105491638[m/m]",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "soil_params.wltsmc",
                    "initial_value": "0.04699999839067459[m/m]",
                    "description": "wilting point soil moisture content",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "max_gw_storage",
                    "initial_value": "0.24887662[m]",
                    "description": "maximum storage in the conceptual reservoir",
                    "min": "0.01",
                    "max": "0.25",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "Cgw",
                    "initial_value": "0.005[m h-1]",
                    "description": "the primary outlet coefficient",
                    "min": "0.0000018",
                    "max": "0.0018",
                    "data_type": "double",
                    "units": "m h-1"
                },
                {
                    "name": "expon",
                    "initial_value": "3.0[]",
                    "description": "exponent parameter (1.0 for linear reservoir)",
                    "min": "1",
                    "max": "8",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "K_lf",
                    "initial_value": "0.1[]",
                    "description": "Nash Config param - primary reservoir",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "refkdt",
                    "initial_value": "2.0[]",
                    "description": "Parameter in the surface runoff parameterization",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "ACTUAL_ET",
                    "description": "Actual ET"
                },
                {
                    "variable": "DEEP_GW_TO_CHANNEL_FLUX",
                    "description": "Groundwater recharge rate to channel "
                },
                {
                    "variable": "DIRECT_RUNOFF",
                    "description": "Surface runoff"
                },
                {
                    "variable": "GIUH_RUNOFF",
                    "description": "Runoff for GIUH routing"
                },
                {
                    "variable": "GW_STORAGE",
                    "description": "Groundwater storage"
                },
                {
                    "variable": "INFILTRATION_EXCESS",
                    "description": "Excess infiltration"
                },
                {
                    "variable": "NASH_LATERAL_RUNOFF",
                    "description": "Lateral runoff"
                },
                {
                    "variable": "NWM_PONDED_DEPTH",
                    "description": "Ponded water depth \t"
                },
                {
                    "variable": "POTENTIAL_ET",
                    "description": "Potential ET"
                },
                {
                    "variable": "Q_OUT",
                    "description": "Streamflow output"
                },
                {
                    "variable": "RAIN_RATE",
                    "description": "Precipitation rate"
                },
                {
                    "variable": "SOIL_STORAGE",
                    "description": "Soil water storage"
                },
                {
                    "variable": "SOIL_STORAGE_CHANGE",
                    "description": "Changes in soil water storage"
                },
                {
                    "variable": "SOIL_TO_GW_FLUX",
                    "description": "Soil to groundwater recharge rate"
                },
                {
                    "variable": "SURF_RUNOFF_SCHEME",
                    "description": "Surface runoff scheme"
                }
            ]
        },
        {
            "module_name": "Noah-OWP-Modular",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/Noah-OWP-Modular/2025_Feb_06_18_02_58"
            },
            "calibrate_parameters": [
                {
                    "name": "bexp",
                    "initial_value": 4.74,
                    "description": "Pore size distribution index (expenontial term)",
                    "min": "0",
                    "max": "20.387",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "MAXSMC",
                    "initial_value": 0.434,
                    "description": "porosity (volumetric)",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "SATDK",
                    "initial_value": 5.23e-06,
                    "description": "saturated conductivity",
                    "min": "0",
                    "max": "0.00141",
                    "data_type": "double",
                    "units": "m/s"
                },
                {
                    "name": "AXAJ",
                    "initial_value": 0.009,
                    "description": "Xinanjiang: Tension water distribution inflection parameter",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "BXAJ",
                    "initial_value": 0.09,
                    "description": "Xinanjiang: Tension water distribution shape parameter",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "XXAJ",
                    "initial_value": 0.09,
                    "description": "Xinanjiang: Free water distribution shape parameter",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "HVT",
                    "initial_value": 16.0,
                    "description": "top of canopy",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "MFSNO",
                    "initial_value": 2.5,
                    "description": "snowmelt curve parameter",
                    "min": "0.625",
                    "max": "5",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "CWPVT",
                    "initial_value": 0.67,
                    "description": "empirical canopy wind parameter",
                    "min": "0.09",
                    "max": "10",
                    "data_type": "double",
                    "units": "1/m"
                },
                {
                    "name": "VCMX25",
                    "initial_value": 60.0,
                    "description": "maximum rate of carboxylation at 25c",
                    "min": "24",
                    "max": "112",
                    "data_type": "double",
                    "units": "umol co2/m**2/s"
                },
                {
                    "name": "MP",
                    "initial_value": 9.0,
                    "description": "slope of conductance-to-photosynthesis relationship",
                    "min": "5.4",
                    "max": "12.6",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "RSURF_SNOW",
                    "initial_value": 50.0,
                    "description": "surface resistence for snow [s/m]",
                    "min": "0.136",
                    "max": "100",
                    "data_type": "double",
                    "units": "s/m"
                },
                {
                    "name": "RSURF_EXP",
                    "initial_value": 5.0,
                    "description": "exponent in the shape parameter for soil resistance option 1",
                    "min": "1",
                    "max": "6",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "SCAMAX",
                    "initial_value": 0.9,
                    "description": "Maximum fractional snow-covered area",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "SLOPE",
                    "initial_value": 0.1,
                    "description": "Linear scaling of \"openness\" of bottom drainage boundary",
                    "min": "0",
                    "max": "1",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "REFKDT",
                    "initial_value": 2e-06,
                    "description": "Surface runoff parameter; REFKDT is a tuneable parameter that significantly impacts surface infiltration and hence the partitioning of total runoff into surface and subsurface runoff. Increasing REFKDT decreases surface runoff",
                    "min": None,
                    "max": None,
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "ACSNOM",
                    "description": " Accumulated meltwater from bottom snow layer (mm) (NWM 3.0 output variable)"
                },
                {
                    "variable": "CMC",
                    "description": " Total canopy water (liquid + ice) (mm) (NWM 3.0 output variable)"
                },
                {
                    "variable": "ECAN",
                    "description": " evaporation of intercepted water (mm) (NWM 3.0 output variable)"
                },
                {
                    "variable": "ETRAN",
                    "description": "transpiration rate (mm/s)"
                },
                {
                    "variable": "EVAPOTRANS",
                    "description": "evapotranspiration rate (m/s)"
                },
                {
                    "variable": "FIRA",
                    "description": " Total net LW radiation to atmosphere (W/m-2) (NWM 3.0 output variable)"
                },
                {
                    "variable": "FSA",
                    "description": " Total absorbed SW radiation (W/m-2) (NWM 3.0 output variable)"
                },
                {
                    "variable": "FSH",
                    "description": " Total sensible heat to the atmosphere (W/m-2) (NWM 3.0 output variable)"
                },
                {
                    "variable": "FSNO",
                    "description": " Snow-cover fraction on the ground ( fraction) (NWM 3.0 output variable)"
                },
                {
                    "variable": "GH",
                    "description": " Heat flux into the soil (W/m-2) (NWM 3.0 output variable)"
                },
                {
                    "variable": "ISNOW",
                    "description": " Number of snow layers () (NWM 3.0 output variable)"
                },
                {
                    "variable": "LH",
                    "description": " Total latent heat to the atmosphere (W/m-2) (NWM 3.0 output variable)"
                },
                {
                    "variable": "QINSUR",
                    "description": "total liquid water input to surface rate (m/s)"
                },
                {
                    "variable": "QRAIN",
                    "description": " Rainfall rate on the ground (mm/s) (NWM 3.0 output variable)"
                },
                {
                    "variable": "QSEVA",
                    "description": "evaporation rate (mm/s)"
                },
                {
                    "variable": "QSNOW",
                    "description": " Snowfall rate on the ground (mm/s) (NWM 3.0 output variable)"
                },
                {
                    "variable": "SNEQV",
                    "description": "snow water equivalent (mm)"
                },
                {
                    "variable": "SNLIQ",
                    "description": " Snow layer liquid water (mm) (NWM 3.0 output variable)"
                },
                {
                    "variable": "SNOWH",
                    "description": " Snow depth (m) (NWM 3.0 output variable)"
                },
                {
                    "variable": "SNOWT_AVG",
                    "description": " Average snow temperature (K) (by layer mass) (NWM 3.0 output variable)"
                },
                {
                    "variable": "TG",
                    "description": "surface/ground temperature (becomes snow surface temperature when snow is present)"
                },
                {
                    "variable": "TGS",
                    "description": "ground temperature (K) (is equal to TG when no snow and equal to bottom snow element temperature when there is snow)"
                },
                {
                    "variable": "TRAD",
                    "description": " Surface radiative temperature (K) (NWM 3.0 output variable)"
                }
            ]
        },
        {
            "module_name": "T-Route",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/T-Route/2025_Feb_06_18_02_59"
            },
            "calibrate_parameters": [],
            "output_variables": [
                {
                    "variable": "channel_exit_water_x-section__volume_flow_rate",
                    "description": "Channel X-Section exit volume flow rate"
                },
                {
                    "variable": "channel_water_flow__speed",
                    "description": "Channel flow speed"
                },
                {
                    "variable": "channel_water__mean_depth",
                    "description": "Channel depth mean"
                },
                {
                    "variable": "lake_surface__elevation",
                    "description": "Lake surface elevation"
                },
                {
                    "variable": "lake_water~incoming__volume_flow_rate",
                    "description": "Lake water incoming volume flow rate"
                },
                {
                    "variable": "lake_water~outgoing__volume_flow_rate",
                    "description": "Lake water outgoing volume flow rate"
                }
            ]
        },
        {
            "module_name": "LASAM",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/LASAM/2025_Feb_10_22_46_21"
            },
            "calibrate_parameters": [
                {
                    "name": "theta_r",
                    "initial_value": "0.095",
                    "description": "residual water content - the minimum volumetric water content that a soil layer can naturally attain",
                    "min": "0.01",
                    "max": "0.15",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "theta_e",
                    "initial_value": "0.41",
                    "description": "the maximum volumetric water content that a soil layer can naturally attain",
                    "min": "0.3",
                    "max": "0.8",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "alpha",
                    "initial_value": "0.019",
                    "description": "the van Genuchton parameter related to the inverse of air entry pressure",
                    "min": "0.001",
                    "max": "0.3",
                    "data_type": "double",
                    "units": "1/cm"
                },
                {
                    "name": "n",
                    "initial_value": "1.31",
                    "description": "the van Genuchton parameter related to pore size distribution",
                    "min": "1.01",
                    "max": "3",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "Ks",
                    "initial_value": "0.26",
                    "description": "the saturated hydraulic conductivity of a soil",
                    "min": "0.001",
                    "max": "100",
                    "data_type": "double",
                    "units": "cm/h"
                },
                {
                    "name": "ponded_depth_max",
                    "initial_value": "1.1",
                    "description": "max amount of water unavailable for surface drainage",
                    "min": "0",
                    "max": "5",
                    "data_type": "double",
                    "units": "cm"
                },
                {
                    "name": "field_capacity_psi",
                    "initial_value": "340.9",
                    "description": "capillary head corresponding to volumetric water content at which gravity drainage becomes slower - used in computing AET",
                    "min": "10.3",
                    "max": "516.6",
                    "data_type": "double",
                    "units": "cm"
                }
            ],
            "output_variables": [
                {
                    "variable": "actual_evapotranspiration",
                    "description": "volume of AET"
                },
                {
                    "variable": "giuh_runoff",
                    "description": "volume of giuh runoff"
                },
                {
                    "variable": "groundwater_to_stream_recharge",
                    "description": "outgoing water from ground reservoir to stream channel"
                },
                {
                    "variable": "infiltration",
                    "description": "volume of infiltrated water"
                },
                {
                    "variable": "mass_balance",
                    "description": "mass balance error"
                },
                {
                    "variable": "percolation",
                    "description": "volume of water leaving soil through the bottom of the domain (ground water recharge)"
                },
                {
                    "variable": "potential_evapotranspiration",
                    "description": "volume of PET"
                },
                {
                    "variable": "precipitation",
                    "description": "total precipitation"
                },
                {
                    "variable": "soil_depth_layers",
                    "description": "Soil depth layers"
                },
                {
                    "variable": "soil_depth_wetting_fronts",
                    "description": "Soil depth wetting fronts"
                },
                {
                    "variable": "soil_moisture_wetting_fronts",
                    "description": "Soil moisture wetting front"
                },
                {
                    "variable": "soil_num_wetting_fronts",
                    "description": "Number of soil wetting fronts"
                },
                {
                    "variable": "soil_storage",
                    "description": "volume of water left"
                },
                {
                    "variable": "surface_runoff",
                    "description": "volume of water surface runoff"
                },
                {
                    "variable": "total_discharge",
                    "description": "total outgoing water"
                }
            ]
        },
        {
            "module_name": "TopModel",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/TopModel/2025_Feb_10_22_46_22"
            },
            "calibrate_parameters": [
                {
                    "name": "t0",
                    "initial_value": "0.000075",
                    "description": "downslope transmissivity when the soil is just saturated to the surface",
                    "min": "0",
                    "max": "0.0001",
                    "data_type": "double",
                    "units": "meters/hour"
                },
                {
                    "name": "td",
                    "initial_value": "20",
                    "description": "unsaturated zone time delay per unit storage deficit",
                    "min": "0.001",
                    "max": "40",
                    "data_type": "double",
                    "units": "hours"
                },
                {
                    "name": "srmax",
                    "initial_value": "0.04",
                    "description": "maximum root zone storage deficit",
                    "min": "0.005",
                    "max": "0.05",
                    "data_type": "double",
                    "units": "meters"
                },
                {
                    "name": "xk0",
                    "initial_value": "2",
                    "description": "surface soil hydraulic conductivity",
                    "min": "0.0001",
                    "max": "0.2",
                    "data_type": "double",
                    "units": "meters/hour"
                },
                {
                    "name": "hf",
                    "initial_value": "0.1",
                    "description": "wetting front suction for G&A soln.",
                    "min": "0.01",
                    "max": "0.5",
                    "data_type": "double",
                    "units": "meters"
                },
                {
                    "name": "dth",
                    "initial_value": "0.1",
                    "description": "water content change across the wetting front; dimensionless",
                    "min": "0.01",
                    "max": "0.6",
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "bal",
                    "description": "land_surface_water__water_balance_volume"
                },
                {
                    "variable": "ep",
                    "description": "water_potential_evaporation_flux_out"
                },
                {
                    "variable": "p",
                    "description": "atmosphere_water__liquid_equivalent_precipitation_rate_out"
                },
                {
                    "variable": "qb",
                    "description": "land_surface_water__baseflow_volume_flux"
                },
                {
                    "variable": "q(it)",
                    "description": "land_surface_water__runoff_mass_flux"
                },
                {
                    "variable": "qof",
                    "description": "land_surface_water__domain_time_integral_of_overland_flow_volume_flux"
                },
                {
                    "variable": "Qout",
                    "description": None
                },
                {
                    "variable": "qz",
                    "description": "soil_water_root-zone_unsat-zone_top__recharge_volume_flux"
                },
                {
                    "variable": "sbar",
                    "description": "soil_water__domain_volume_deficit"
                },
                {
                    "variable": "sumae",
                    "description": "land_surface_water__domain_time_integral_of_evaporation_volume_flux"
                },
                {
                    "variable": "sump",
                    "description": "land_surface_water__domain_time_integral_of_precipitation_volume_flux"
                },
                {
                    "variable": "sumq",
                    "description": "land_surface_water__domain_time_integral_of_runoff_volume_flux"
                },
                {
                    "variable": "sumrz",
                    "description": "soil_water__domain_root-zone_volume_deficit"
                },
                {
                    "variable": "sumuz",
                    "description": "soil_water__domain_unsaturated-zone_volume"
                }
            ]
        },
        {
            "module_name": "SFT",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/SFT/2025_Feb_10_22_46_22"
            },
            "calibrate_parameters": [
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.4009084105491638",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.027170022789296738",
                    "description": "saturated capillary head",
                    "min": "0.03",
                    "max": "0.955",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "soil_params.b",
                    "initial_value": "7.551834583282471",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": "2",
                    "max": "15",
                    "data_type": "double",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "ground_heat_flux",
                    "description": None
                },
                {
                    "variable": "ice_fraction_schaake",
                    "description": "ice_fraction_schaake flag"
                },
                {
                    "variable": "ice_fraction_xinanjiang",
                    "description": None
                },
                {
                    "variable": "num_cells",
                    "description": None
                },
                {
                    "variable": "soil_ice_fraction",
                    "description": "soil_ice_fraction"
                },
                {
                    "variable": "soil_temperature_profile",
                    "description": None
                }
            ]
        },
        {
            "module_name": "SMP",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/SMP/2025_Feb_10_22_46_23"
            },
            "calibrate_parameters": [
                {
                    "name": "soil_params.b",
                    "initial_value": "7.551834583282471",
                    "description": "beta exponent on Clapp-Hornberger (1978) soil water relations",
                    "min": "2",
                    "max": "15",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "soil_params.satpsi",
                    "initial_value": "0.027170022789296738",
                    "description": "saturated capillary head",
                    "min": "0.03",
                    "max": "0.955",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "soil_params.smcmax",
                    "initial_value": "0.4009084105491638",
                    "description": "saturated soil moisture content",
                    "min": None,
                    "max": "1",
                    "data_type": "double",
                    "units": "m/m"
                }
            ],
            "output_variables": [
                {
                    "variable": "soil_moisture_fraction",
                    "description": "**Note: SoilMoistureProfiles has a bmi output called soil_moisture_fraction (water in the topsoil over total water in the soil column) needs the depth of the topsoil (soil_moisture_fraction_depth, default is set to 40 cm -- the top two cells in the soil column of the NWM 3.0)"
                },
                {
                    "variable": "soil_moisture_profile",
                    "description": "Entire profile of the soil column (1D array)"
                },
                {
                    "variable": "soil_moisture_profile",
                    "description": "Entire profile of the soil column (1D array)"
                },
                {
                    "variable": "soil_water_table",
                    "description": "Depth of the water table from the surface in meters"
                },
                {
                    "variable": "soil_water_table",
                    "description": "Depth of the water table from the surface in meters"
                }
            ]
        },
        {
            "module_name": "UEB",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/UEB/2025_Feb_18_21_42_13"
            },
            "calibrate_parameters": [
                {
                    "name": "df",
                    "initial_value": "1",
                    "description": "Drift factor multiplier",
                    "min": "0.5",
                    "max": "6",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "cc",
                    "initial_value": "0.4",
                    "description": "Canopy coverage fraction",
                    "min": "0",
                    "max": "0.8",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "hcan",
                    "initial_value": "5",
                    "description": "Canopy height",
                    "min": "0",
                    "max": "10",
                    "data_type": "integer",
                    "units": "m"
                },
                {
                    "name": "lai",
                    "initial_value": "2",
                    "description": "Leaf area index",
                    "min": "0",
                    "max": "4",
                    "data_type": "integer",
                    "units": None
                },
                {
                    "name": "subalb",
                    "initial_value": "0.25",
                    "description": "The fraction of shortwave radiation (fraction 0-1) reflected by the substrate beneath the snow (ground or glacier)",
                    "min": "0.25",
                    "max": "0.7",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "ems",
                    "initial_value": "0.99",
                    "description": "Emissivity of snow",
                    "min": ".98",
                    "max": ".99",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "cg",
                    "initial_value": "2.09",
                    "description": "Ground heat capacity",
                    "min": "2.09",
                    "max": "2.12",
                    "data_type": "double",
                    "units": "KJ/kg/˚C"
                },
                {
                    "name": "zo",
                    "initial_value": "0.010",
                    "description": "Roughness length",
                    "min": "0.0002\n",
                    "max": "0.014",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "rho",
                    "initial_value": "450",
                    "description": "Snow density",
                    "min": "100",
                    "max": "600",
                    "data_type": "double",
                    "units": "kg/m3"
                },
                {
                    "name": "rhog",
                    "initial_value": "1700",
                    "description": "Soil density\n",
                    "min": "1100\n",
                    "max": "1700\n",
                    "data_type": "double",
                    "units": "kg/m3"
                },
                {
                    "name": "Ks",
                    "initial_value": "20",
                    "description": "Snow saturated hydraulic conductivity\n",
                    "min": "0",
                    "max": "20",
                    "data_type": "integer",
                    "units": "m/hr\n"
                },
                {
                    "name": "de",
                    "initial_value": ".1",
                    "description": "Thermally active soil depth",
                    "min": ".1",
                    "max": ".4",
                    "data_type": "double",
                    "units": "m"
                },
                {
                    "name": "avo",
                    "initial_value": ".95",
                    "description": "Visual new snow albedo\n",
                    "min": ".85",
                    "max": ".95\n",
                    "data_type": "double\n",
                    "units": None
                }
            ],
            "output_variables": [
                {
                    "variable": "Alb",
                    "description": "The fraction of shortwave radiation reflected by the snow surface.  "
                },
                {
                    "variable": "atff",
                    "description": "The fraction of radiation at the top of the atmosphere that reaches the top of the canopy or in its absence the snow surface."
                },
                {
                    "variable": "Cf",
                    "description": "The fraction (between 0 and 1) of the sky occupied by clouds."
                },
                {
                    "variable": "conZen",
                    "description": "Cosine of solar illumination angle (accounts for slope)"
                },
                {
                    "variable": "cumes",
                    "description": "Cumulative sublimation from beginning of model run "
                },
                {
                    "variable": "cumMr",
                    "description": "Cumulative melt outflow from beginning of model run"
                },
                {
                    "variable": "cump",
                    "description": "Cumulative precipitation from beginning of model run"
                },
                {
                    "variable": "Day",
                    "description": "Day of beginning of time step (integer)"
                },
                {
                    "variable": "dHour",
                    "description": "Hour of beginning of time step (may be fraction)"
                },
                {
                    "variable": "Eacl",
                    "description": "Clear sky emissivity quantifies the emission of longwave radiation energy from a cloud free atmosphere towards the surface relative to black body radiation at the air temperature"
                },
                {
                    "variable": "Ec",
                    "description": "The flux expressed as snow water equivalent of removal of snow from canopy interception by sublimation.  This is positive away from the canopy. "
                },
                {
                    "variable": "Ema",
                    "description": "Atmospheric emissivity quantifies the emission of longwave radiation energy from the atmosphere towards the surface relative to black body radiation at the air temperature.  The emission from clouds is included"
                },
                {
                    "variable": "errMB",
                    "description": "A running total of the sum of all inputs to and outputs from the model.  Theoretically this should be 0 but practically differs from 0 due to numerical precision and rounding errors in the computation.  It is included as a check on the functioning of the model and if significantly different from 0 is indicative of a problem."
                },
                {
                    "variable": "Es",
                    "description": "Amount of water removed from the snow surface by sublimation"
                },
                {
                    "variable": "FM",
                    "description": "The net sum of all surface layer mass fluxes"
                },
                {
                    "variable": "FMc",
                    "description": "The net sum of all canopy mass fluxes "
                },
                {
                    "variable": "HRI",
                    "description": "Integration of solar radiation incident angle cosine over time step. When radiation data is not input IRAD flag (in param.dat file) set to 0 incoming solar radiation is calculated as Tf * HRI * Solar constant."
                },
                {
                    "variable": "ieff",
                    "description": "Fraction of precipitation intercepted by the canopy"
                },
                {
                    "variable": "Inmax",
                    "description": "Maximum amount of snow that a canopy can hold during a snowfall.  This is a function of maximum snow load per unit leaf area leaf area index and the density of fresh snow."
                },
                {
                    "variable": "intc",
                    "description": "The flux if precipitation that is intercepted by the canopy.  This is a function of the interception capacity and intercepted snow state variable."
                },
                {
                    "variable": "Mc",
                    "description": "The flux expressed as snow water equivalent of removal of snow from canopy interception by melting.  This is subtracted from the intercepted snow and added to surface snow."
                },
                {
                    "variable": "Month",
                    "description": "Month of beginning of time step (integer)"
                },
                {
                    "variable": "NetRads",
                    "description": "Modeled net radiation exchange between the snow surface and atmosphere above and canopy above if present."
                },
                {
                    "variable": "P",
                    "description": "Precipitation that is the sum of both rain and snowfall expressed as water equivalent"
                },
                {
                    "variable": "Pr",
                    "description": "Amount of precipitation that occurred in the form of rain at any time step"
                },
                {
                    "variable": "Ps",
                    "description": "Amount of precipitation that occurred in the form of snow at any time step expressed as water equivalent"
                },
                {
                    "variable": "Q",
                    "description": "The net sum of all surface layer (snow plus thermally interacting substrate) energy fluxes"
                },
                {
                    "variable": "Qec",
                    "description": "Latent energy flux from the air within the canopy to the canopy.  This is positive towards the canopy and is calculated based on the vapor pressure gradient and bulk leaf boundary layer resistance.  It represents the energy flux associated with the phase change due to sublimation (removal) or condensation/deposition (addition) of canopy intercepted snow from water vapor in the air."
                },
                {
                    "variable": "QEs",
                    "description": "Surface latent heat flux is the flux of energy transferred from the snow surface to the atmosphere by water vapor carried in air movement (wind and turbulence)."
                },
                {
                    "variable": "QHc",
                    "description": "Energy flux from the air within the canopy to the canopy.  This is positive towards the canopy and is calculated based on temperature gradient and bulk leaf boundary layer resistance.  "
                },
                {
                    "variable": "QHs",
                    "description": "Surface sensible heat flux is the flux of energy transferred from the snow surface to the atmosphere by air movement (wind and turbulence)."
                },
                {
                    "variable": "Qli",
                    "description": "Modeled incoming longwave radiation"
                },
                {
                    "variable": "Qlnc",
                    "description": "Amount of longwave radiation absorbed in canopy"
                },
                {
                    "variable": "Qlns",
                    "description": "Amount of longwave radiation absorbed at snow surface"
                },
                {
                    "variable": "Qmc",
                    "description": "The flux of energy removed from the canopy due to melt.  This represents the energy flux due to the latent heat of fusion energy difference between melt water and the reference condition of 0 °C solid phase.  This is subtracted from the canopy and added to the surface snow energy content. "
                },
                {
                    "variable": "QMs",
                    "description": "Energy removed from the snowpack by total outflow  "
                },
                {
                    "variable": "Qnet",
                    "description": "Observed net radiation that was input to the model"
                },
                {
                    "variable": "Qpc",
                    "description": "The flux of energy added to the canopy by interception.  This represents the flux due to the energy difference between the phase and temperature of precipitation and the reference condition of 0 °C solid phase."
                },
                {
                    "variable": "Qsi",
                    "description": "Modeled incoming shortwave radiation accounting for slope and aspect of the surface.  This may be different from input Qsi for sloping surfaces"
                },
                {
                    "variable": "Qsib",
                    "description": "The incident solar radiation received at the surface or top of canopy if present as direct solar radiation."
                },
                {
                    "variable": "Qsid",
                    "description": "The incident solar radiation received at the surface or top of canopy if present as diffuse solar radiation."
                },
                {
                    "variable": "Qsnc",
                    "description": "Amount of solar radiation absorbed in canopy"
                },
                {
                    "variable": "Qsns",
                    "description": "Amount of solar radiation absorbed at snow surface"
                },
                {
                    "variable": "refDepth",
                    "description": "The depth of a refreezing front that is active in impacting surface temperature.  This quantifies the depth that refreezing has propagated into the snowpack where liquid water is present.  This is reset to 0 when it exceeds the depth to which diurnal temperature fluctuations propagate and refreezing becomes inactive in snow surface temperature and energy exchange.  "
                },
                {
                    "variable": "RH",
                    "description": "Relative humidity at a point z m above the snow surface or top of canopy if present"
                },
                {
                    "variable": "Smelt",
                    "description": "Amount of melt generated at the snow surface due to rain snowmelt or glacier melt. Smelt does not include snow melt from the canopy.  Smelt also does not equate to melt outflow since it infiltrates into the snow and is subject to refreezing or liquid retention depending on the thermal state of the snow."
                },
                {
                    "variable": "SWE",
                    "description": "State variable that gives the Snow Water Equivalent (SWE) of snow on the surface.  It can be considered as the depth of water that would theoretically result if the whole snow pack instantaneously melts.  This tracks snow accumulation and ablation on top of a substrate layer which may be ground or glacier.  In the case that the substrate is glacier this does not track the quantity of glacier ice."
                },
                {
                    "variable": "SWIGM",
                    "description": "The part of outflow from the base of the snowpack and glacier that is generated from glacier melting. SWIGM includes melt originating from glacial ice as well as outflow that may occur due to rain on a glacier as any precipitation that falls on the snow or glacier surface is first added to the snow/glacier to account for its energy in the total energy content then melt outflow occurs if the energy content results in liquid water in excess of the liquid holding capacity."
                },
                {
                    "variable": "SWIR",
                    "description": "The part of outflow that is due to rain or snow that immediately melts.  This only occurs on a non-glacier surface and when the surface snow water equivalent is 0.  Precipitation that is rain or that is snow that immediately melts due to a high temperature of the thermally active ground layer comprises this outflow."
                },
                {
                    "variable": "SWISM",
                    "description": "The part of outflow that is due to the melting of the seasonal snow pack.  SWISM includes melt originating from the seasonal snow as well as outflow that may occur due to rain on a snowpack as any precipitation that falls on the snow or glacier surface is first added to the snow/glacier to account for its energy in the total energy content then melt outflow occurs if the energy content results in liquid water in excess of the liquid holding capacity.  If surface snow is present then melt outflow is generated from the surface snow.  Glacier melt outflow is only generated when the surface snow water equivalent ablates to 0 and the substrate is glacier."
                },
                {
                    "variable": "SWIT",
                    "description": "Total outflow from the base of the snowpack (and glacier). This includes rainfall melt from seasonal snow and melt from glaciated surface."
                },
                {
                    "variable": "Ta",
                    "description": "Air temperature at a point z m above the snow surface or top of canopy if present"
                },
                {
                    "variable": "Tac",
                    "description": "Temperature of air within the canopy.  This is used in the calculation of energy fluxes between the canopy and within canopy air and in the calculation of energy fluxes between within canopy air and the atmosphere above and snow surface below."
                },
                {
                    "variable": "Taub",
                    "description": "The fraction of direct solar radiation incident at the top of the canopy that is transmitted through the canopy as direct solar radiation without being scattered or absorbed."
                },
                {
                    "variable": "Taud",
                    "description": "The fraction of diffuse solar radiation incident at the top of the canopy that is transmitted through the canopy without being scattered or absorbed.    "
                },
                {
                    "variable": "Taufb",
                    "description": "The part of the atmospheric transmissivity that quantifies direct solar radiation defined as the ratio of top of atmosphere radiation to direct solar radiation at the surface or top of canopy if present. "
                },
                {
                    "variable": "Taufd",
                    "description": "The part of the atmospheric transmissivity that quantifies diffuse solar radiation defined as the ratio of top of atmosphere radiation to diffuse solar radiation at the surface or top of canopy if present. "
                },
                {
                    "variable": "tausn",
                    "description": "Dimensionless age of the snow surface state variable to account for aging of the snow surface dependent on snow surface temperature and snowfall"
                },
                {
                    "variable": "Tave",
                    "description": "Average temperature of the snow and thermally interacting substrate."
                },
                {
                    "variable": "Tc",
                    "description": "Temperature of the leaves and branches within the canopy.  This is used in the calculation of energy fluxes between the canopy and within canopy air. "
                },
                {
                    "variable": "totalRefDepth",
                    "description": "The depth the refreezing front has propagated into the snowpack where liquid water is present.  This is physically the same as RefDepAct but is not set to 0 when it exceeds the depth to which diurnal temperature fluctuations propagate so records refreezing depth whenever there has been refreezing and there is still liquid water present."
                },
                {
                    "variable": "TSURFs",
                    "description": "Temperature at the surface of the snow"
                },
                {
                    "variable": "Ur",
                    "description": "The flux of snow unloaded from the canopy.  Unloading rate is the intercepted snow state variable times the unloading rate coefficient and represents the transfer of snow from the canopy to the surface.  It quantifies snow water equivalent removed from the canopy and added to the surface snow water equivalent. "
                },
                {
                    "variable": "Us",
                    "description": "State variable that gives the energy content of the snow pack plus thermally active soil per unit of horizontal area defined with respect to solid (ice) phase snow at 0 °C.."
                },
                {
                    "variable": "V",
                    "description": "Wind speed at a point z m above the snow surface or top of canopy if present"
                },
                {
                    "variable": "Vz",
                    "description": "Modeled wind speed beneath canopy at height z above the surface"
                },
                {
                    "variable": "Wc",
                    "description": "Intercepted snow state variable giving the water equivalent of snow held as interception in the canopy."
                },
                {
                    "variable": "Year",
                    "description": "Year of beginning of time step (integer)"
                }
            ]
        },
        {
            "module_name": "Sac-SMA",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/Sac-SMA/2025_Feb_10_22_46_33"
            },
            "calibrate_parameters": [
                {
                    "name": "uztwm",
                    "initial_value": "35.0968437194824",
                    "description": "upper zone tension water maximum storage",
                    "min": "25",
                    "max": "125",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "uzfwm",
                    "initial_value": "30.4247760772705",
                    "description": "Maximum upper zone free water",
                    "min": "10",
                    "max": "75",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lztwm",
                    "initial_value": "186.607803344727",
                    "description": "Maximum lower zone tension water",
                    "min": "75",
                    "max": "300",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lzfsm",
                    "initial_value": "21.6620540618896",
                    "description": "Maximum lower zone free water, secondary (aka supplemental)",
                    "min": "15",
                    "max": "300",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "lzfpm",
                    "initial_value": "141.267791748047",
                    "description": "Maximum lower zone free water, primary",
                    "min": "40",
                    "max": "600",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "adimp",
                    "initial_value": "0.0",
                    "description": "Additional impervious area due to saturation",
                    "min": "0",
                    "max": "0.2",
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "uzk",
                    "initial_value": "0.483688116073608",
                    "description": "Upper zone recession coefficient",
                    "min": "0.2",
                    "max": "0.5",
                    "data_type": "double",
                    "units": "per day "
                },
                {
                    "name": "lzpk",
                    "initial_value": "0.0310279987752438",
                    "description": "Lower zone recession coefficient, primary",
                    "min": "0.001",
                    "max": "0.015",
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "lzsk",
                    "initial_value": "0.177159339189529",
                    "description": "Lower zone recession coefficient, secondary (aka supplemental)",
                    "min": "0.03",
                    "max": "0.2",
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "zperc",
                    "initial_value": "48.3430290222168",
                    "description": "Minimum percolation rate coefficient",
                    "min": "20",
                    "max": "300",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "rexp",
                    "initial_value": "1.84926867485046",
                    "description": "Percolation equation exponent",
                    "min": "1.4",
                    "max": "3.5",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "pctim",
                    "initial_value": "0.0",
                    "description": "impervious  fraction of the watershed area ",
                    "min": "0",
                    "max": "0.05",
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "pfree",
                    "initial_value": "0.185674577951431",
                    "description": "fraction of water percolating from upper zone directly to lower zone free water storage. ",
                    "min": "0",
                    "max": "0.5",
                    "data_type": "double",
                    "units": "decimal percent"
                },
                {
                    "name": "riva",
                    "initial_value": "0.0",
                    "description": "Percent of the basin that is riparian area",
                    "min": "0",
                    "max": "0.2",
                    "data_type": "double",
                    "units": "decimal percent"
                }
            ],
            "output_variables": [
                {
                    "variable": "bfncc",
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
            "module_name": "Snow-17",
            "parameter_file": {
                "uri": "s3://ngwpc-hydrofabric/2.2/CONUS/01123000/PARAMS/USGS/Snow-17/2025_Feb_06_19_30_50"
            },
            "calibrate_parameters": [
                {
                    "name": "mfmax",
                    "initial_value": "1.57277953624725",
                    "description": " Maximum melt factor during non-rain periods – assumed to occur on June 21",
                    "min": "0.7",
                    "max": "2.4",
                    "data_type": "double",
                    "units": "mm/˚C/6 hr"
                },
                {
                    "name": "uadj",
                    "initial_value": "0.0571748986840248",
                    "description": " The average wind function during rain-on-snow periods",
                    "min": "0.02",
                    "max": "0.4",
                    "data_type": "double",
                    "units": "mm/mb/6 hr"
                },
                {
                    "name": "si",
                    "initial_value": "500.00",
                    "description": " The mean areal water equivalent above which there is always 100 percent areal snow cover",
                    "min": "10",
                    "max": "120",
                    "data_type": "double",
                    "units": "mm"
                },
                {
                    "name": "adc1",
                    "initial_value": "0.050",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.050",
                    "max": "0.050",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc2",
                    "initial_value": "0.100",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.100",
                    "max": "0.100",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc3",
                    "initial_value": "0.200",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.200",
                    "max": "0.200",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc4",
                    "initial_value": "0.300",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.300",
                    "max": "0.300",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc5",
                    "initial_value": "0.400",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.400",
                    "max": "0.400",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc6",
                    "initial_value": "0.500",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.500",
                    "max": "0.500",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc7",
                    "initial_value": "0.600",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.600",
                    "max": "0.600",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc8",
                    "initial_value": "0.700",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.700",
                    "max": "0.700",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "mfmin",
                    "initial_value": "0.378186523914337",
                    "description": " Minimum melt factor during non-rain periods – assumed to occur on December 21",
                    "min": "0.0001",
                    "max": "1.5",
                    "data_type": "double",
                    "units": "mm/˚C/6 hr"
                },
                {
                    "name": "scf",
                    "initial_value": "1.100",
                    "description": "The multiplying factor which adjusts precipitation that is determined to be in the form of snow",
                    "min": "1",
                    "max": "1.3",
                    "data_type": "double",
                    "units": ""
                },
                {
                    "name": "adc9",
                    "initial_value": "0.800",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.800",
                    "max": "0.800",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc10",
                    "initial_value": "0.900",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "0.900",
                    "max": "0.900",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "adc11",
                    "initial_value": "1.000",
                    "description": " Curve that defines the areal extent of the snow cover as a function of how much of the original snow cover remains after significant bare ground shows up",
                    "min": "1.000",
                    "max": "1.000",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "nmf",
                    "initial_value": "0.150",
                    "description": " Maximum negative melt factor",
                    "min": "0.05",
                    "max": "0.3",
                    "data_type": "double",
                    "units": "mm/˚C/6 hr"
                },
                {
                    "name": "tipm",
                    "initial_value": "0.100",
                    "description": " Antecedent temperature index parameter",
                    "min": "0.05",
                    "max": "0.2",
                    "data_type": "double",
                    "units": None
                },
                {
                    "name": "pxtemp",
                    "initial_value": "1.000",
                    "description": " Antecedent temperature index parameter",
                    "min": "-1",
                    "max": "3",
                    "data_type": "double",
                    "units": "˚C"
                },
                {
                    "name": "mbase",
                    "initial_value": "0.000",
                    "description": "  Base temperature for snowmelt computations during non-rain periods",
                    "min": "0.000",
                    "max": "0.000",
                    "data_type": "double",
                    "units": "˚C"
                },
                {
                    "name": "plwhc",
                    "initial_value": "0.030",
                    "description": " maximum amount of liquid water as a fraction of the ice portion of the snow that can be held against gravity drainage",
                    "min": "0.02",
                    "max": "0.3",
                    "data_type": "double",
                    "units": " %"
                },
                {
                    "name": "daygm",
                    "initial_value": "0.000",
                    "description": " Constant daily amount of melt which takes place at the snow-soil interface whenever there is a snow cover",
                    "min": "0.000",
                    "max": "0.3",
                    "data_type": "double",
                    "units": "mm/day"
                }
            ],
            "output_variables": [
                {
                    "variable": "cs",
                    "description": "19-element vector per HRU used in snow19: (n_hrus, 19)"
                },
                {
                    "variable": "raim",
                    "description": "rain and melt output"
                },
                {
                    "variable": "raim_comb",
                    "description": None
                },
                {
                    "variable": "sneqv",
                    "description": "snow water equivalent"
                },
                {
                    "variable": "sneqv_comb",
                    "description": None
                },
                {
                    "variable": "snow",
                    "description": "snow"
                },
                {
                    "variable": "snowh",
                    "description": "snow height"
                },
                {
                    "variable": "snowh_comb\n",
                    "description": None
                }
            ]
        }
    ]
}
