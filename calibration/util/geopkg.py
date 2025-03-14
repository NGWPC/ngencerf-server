import argparse
import json
import os
from functools import lru_cache
from io import BytesIO
from itertools import cycle

import fiona
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt

# See https://stackoverflow.com/questions/27147300/matplotlib-tcl-asyncdelete-async-handler-deleted-by-the-wrong-thread
matplotlib.use('Agg')  # Use a backend that doesn't require a display (like for generating images)


def check_file_accessible(file_path: str) -> None:
    """
    Checks if a file exists, is a valid file (not a directory), and is readable.

    :param file_path: Path to the file.
    :raises FileNotFoundError: If the file does not exist.
    :raises IsADirectoryError: If the file path is a directory instead of a file.
    :raises PermissionError: If the file exists but is not readable.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"GeoPackage file not found: {file_path}")
    if not os.path.isfile(file_path):
        raise IsADirectoryError(f"Expected a file but found a directory: {file_path}")
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"Permission denied: {file_path}")


def safe_read_gpkg(gpkg_path: str, layer: str = None) -> gpd.GeoDataFrame:
    """
    Safely reads a layer from a GeoPackage file, providing detailed error messages.

    :param gpkg_path: Path to the GeoPackage file.
    :param layer: Name of the layer to read (reads default layer if None).
    :return: GeoDataFrame containing the layer data.
    :raises RuntimeError: If reading fails due to corruption, invalid format, or missing drivers.
    """
    try:
        return gpd.read_file(gpkg_path, layer=layer)
    except fiona.errors.DriverError as e:
        raise RuntimeError(f"Could not open {gpkg_path}. Ensure it is a valid GeoPackage. Error: {e}")
    except Exception as e:
        raise RuntimeError(
            f"Failed to read '{layer}' layer from {gpkg_path}. Possible issues:\n"
            f"  - File exists: {os.path.exists(gpkg_path)}\n"
            f"  - File size: {os.path.getsize(gpkg_path) if os.path.exists(gpkg_path) else 'N/A'} bytes\n"
            f"  - Available layers: {fiona.listlayers(gpkg_path) if os.path.exists(gpkg_path) else 'N/A'}\n"
            f"Error details: {e}"
        )


def gpkg_to_png(gpkg_path: str, png_path: str, layer: str = None) -> None:
    """
    Generates a PNG image from a specific layer in a GeoPackage.

    :param gpkg_path: Path to the GeoPackage file.
    :param png_path: Path where the generated PNG file will be saved.
    :param layer: Name of the layer to visualize, or None to visualize all layers.
    :raises FileNotFoundError: If the GeoPackage file does not exist.
    """
    check_file_accessible(gpkg_path)
    gdf = safe_read_gpkg(gpkg_path, layer)

    # Plot the GeoDataFrame
    fig, ax = plt.subplots(1, 1, figsize=(15, 15))
    gdf.plot(ax=ax, cmap='viridis')

    # Remove axes for better visualization
    ax.set_axis_off()

    # Save the plot as a PNG file
    plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    plt.close()


@lru_cache()
def gpkg_to_png_selected_layers(gpkg_path: str, layers_to_include: tuple[str, ...] = None) -> BytesIO:
    """
    Generates a PNG image from selected layers in a GeoPackage and returns it as a BytesIO object.

    :param gpkg_path: Path to the GeoPackage file.
    :param layers_to_include: Tuple of layer names to include in the plot. Defaults to a predefined set.
    :return: BytesIO object containing the generated PNG image.
    :raises FileNotFoundError: If the GeoPackage file does not exist.
    """
    check_file_accessible(gpkg_path)

    if layers_to_include is None:
        layers_to_include = ('nexus', 'flowpaths', 'flowlines')  # Default layers to include

    # Initialize the plot
    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)

    # Track which layers have been labeled
    labeled_layers = set()

    try:
        available_layers = fiona.listlayers(gpkg_path)
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve layers from GeoPackage: {gpkg_path}. Error: {e}")

    # Plot the divides layer (outline) if it exists
    if 'divides' in available_layers:
        try:
            divides_gdf = safe_read_gpkg(gpkg_path, layer='divides')
            # Simplify geometries for performance improvement
            divides_gdf['geometry'] = divides_gdf['geometry'].simplify(tolerance=0.01, preserve_topology=True)
            divides_gdf.boundary.plot(ax=ax, color='black', label='divides' if 'divides' not in labeled_layers else None)
            labeled_layers.add('divides')
        except Exception as e:
            raise RuntimeError(f"Failed to read 'divides' layer from {gpkg_path}. Error: {e}")

    # Define a cycle of colors for the layers
    color_cycle = cycle(['blue', 'green', 'red', 'cyan', 'magenta'])

    # Plot each requested layer if it exists
    for layer, color in zip(layers_to_include, color_cycle):
        if layer in available_layers:
            try:
                layer_gdf = safe_read_gpkg(gpkg_path, layer=layer)
                # Simplify geometries for performance improvement
                layer_gdf['geometry'] = layer_gdf['geometry'].simplify(tolerance=0.01, preserve_topology=True)
                # Plot the entire layer at once
                layer_gdf.plot(ax=ax, color=color, label=layer if layer not in labeled_layers else None)
                labeled_layers.add(layer)
            except Exception as e:
                raise RuntimeError(f"Failed to read '{layer}' layer from {gpkg_path}. Error: {e}")

    # Add a legend explicitly
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc='upper right')

    # Remove axes for better visualization
    ax.set_axis_off()

    # Save the plot as a PNG file
    # plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    # plt.close()

    # Convert the plot to an in-memory PNG file
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close()
    img_buffer.seek(0)
    return img_buffer


@lru_cache()
def get_geometry_from_gpkg(gpkg_path: str, catchment_layer: str = None, gage_layer: str = None) -> dict:
    """
    Extracts both catchment boundaries (as WKT) and gage coordinates (latitude & longitude) from a GeoPackage.

    :param gpkg_path: Path to the GeoPackage file.
    :param catchment_layer: Name of the layer containing catchment boundaries. Defaults to 'divides'.
    :param gage_layer: Name of the layer containing gage locations. Defaults to 'hydrolocations'.
    :return: Dictionary containing:
             - "catchments": Mapping of catchment identifiers to their boundaries as WKT strings.
             - "gage_coordinates": Dictionary with 'latitude' and 'longitude'.
             - "crs": The coordinate reference system of the layers.
    :raises RuntimeError: If reading fails.
    :raises ValueError: If the specified layers or required columns are missing.
    """
    if catchment_layer is None:
        catchment_layer = "divides"
    if gage_layer is None:
        gage_layer = "hydrolocations"

    check_file_accessible(gpkg_path)

    # List all layers to verify the requested layers exist
    try:
        available_layers = fiona.listlayers(gpkg_path)
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve layers from GeoPackage: {gpkg_path}. Error: {e}")

    if catchment_layer not in available_layers:
        raise ValueError(f"Catchment layer '{catchment_layer}' not found. Available layers: {available_layers}")

    if gage_layer not in available_layers:
        raise ValueError(f"Gage layer '{gage_layer}' not found. Available layers: {available_layers}")

    # Read the catchments layer
    gdf_catchments = safe_read_gpkg(gpkg_path, layer=catchment_layer)

    # Extract catchments, converting geometry to WKT
    if 'divide_id' not in gdf_catchments.columns or 'geometry' not in gdf_catchments.columns:
        raise ValueError("The required columns ('divide_id', 'geometry') were not found in the catchment layer.")

    catchments = {
        row['divide_id']: row['geometry'].wkt  # Convert to WKT (string)
        for _, row in gdf_catchments.iterrows()
    }

    # Read the gage layer
    gdf_gage = safe_read_gpkg(gpkg_path, layer=gage_layer)

    # Ensure gage data exists and convert coordinates
    if gdf_gage.empty or 'hl_x' not in gdf_gage.columns or 'hl_y' not in gdf_gage.columns:
        gage_coordinates = None  # No valid gage data found
    else:
        # Convert hl_x, hl_y into a GeoDataFrame
        gdf_gage = gdf_gage.set_geometry(gpd.points_from_xy(gdf_gage.hl_x, gdf_gage.hl_y))

        # Assign CRS from Catchments if Gage CRS is missing
        if gdf_gage.crs is None:
            if gdf_catchments.crs:
                gdf_gage.set_crs(gdf_catchments.crs, inplace=True)
            else:
                raise RuntimeError("CRS is missing for both the gage and catchments layers. Cannot convert to latitude/longitude.")

        # Convert to EPSG:4326 (WGS84 lat/lon)
        gdf_gage = gdf_gage.to_crs(epsg=4326)
        gage_point = gdf_gage.geometry.iloc[0]  # Assuming first entry is the gage
        gage_coordinates = {"latitude": gage_point.y, "longitude": gage_point.x}

    return {
        "catchments": catchments,
        "gage_coordinates": gage_coordinates,
        "crs": gdf_catchments.crs.to_string() if gdf_catchments.crs else None
    }


def main():
    parser = argparse.ArgumentParser(description="GeoPackage Catchments Extraction Tool")
    parser.add_argument("gpkg_path", type=str, help="Path to the GeoPackage file")
    parser.add_argument("--layer", type=str, default="divides", help="Layer name containing catchments (default: 'divides')")
    args = parser.parse_args()

    try:
        catchments_data = get_geometry_from_gpkg(args.gpkg_path, args.layer)
        print(json.dumps(catchments_data, indent=4, default=str))
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
