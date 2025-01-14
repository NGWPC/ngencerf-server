from functools import lru_cache
from io import BytesIO
from itertools import cycle
from typing import Tuple

import fiona
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt

# See https://stackoverflow.com/questions/27147300/matplotlib-tcl-asyncdelete-async-handler-deleted-by-the-wrong-thread
matplotlib.use('Agg')  # Use a backend that doesn't require a display (like for generating images)


def gpkg_to_png(gpkg_path: str, png_path: str, layer: str | None = None) -> None:
    """
    Generates a PNG image from a specific layer in a GeoPackage.

    :param gpkg_path: Path to the GeoPackage file.
    :param png_path: Path where the generated PNG file will be saved.
    :param layer: Name of the layer to visualize, or None to visualize all layers.
    """
    # Read the GeoPackage file
    gdf = gpd.read_file(gpkg_path, layer=layer) if layer else gpd.read_file(gpkg_path)

    # Plot the GeoDataFrame
    fig, ax = plt.subplots(1, 1, figsize=(15, 15))
    gdf.plot(ax=ax, cmap='viridis')

    # Remove axes for better visualization
    ax.set_axis_off()

    # Save the plot as a PNG file
    plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    plt.close()


@lru_cache(maxsize=128)
def gpkg_to_png_selected_layers(gpkg_path: str, layers_to_include: Tuple[str, ...] | None = None) -> BytesIO:
    """
    Generates a PNG image from selected layers in a GeoPackage and returns it as a BytesIO object.

    :param gpkg_path: Path to the GeoPackage file.
    :param layers_to_include: Tuple of layer names to include in the plot. Defaults to a predefined set.
    :return: BytesIO object containing the generated PNG image.
    """
    if layers_to_include is None:
        layers_to_include = ('nexus', 'flowpaths', 'flowlines')  # Default layers to include

    # Initialize the plot
    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)

    # Track which layers have been labeled
    labeled_layers = set()

    # Plot the divides layer (outline) if it exists
    if 'divides' in fiona.listlayers(gpkg_path):
        divides_gdf = gpd.read_file(gpkg_path, layer='divides')
        # Simplify geometries for performance improvement
        divides_gdf['geometry'] = divides_gdf['geometry'].simplify(tolerance=0.01, preserve_topology=True)
        divides_gdf.boundary.plot(ax=ax, color='black', label='divides' if 'divides' not in labeled_layers else None)
        labeled_layers.add('divides')

    # Define a cycle of colors for the layers
    color_cycle = cycle(['blue', 'green', 'red', 'cyan', 'magenta'])

    # Get available layers from the GeoPackage
    available_layers = fiona.listlayers(gpkg_path)

    # Plot each requested layer if it exists
    for layer, color in zip(layers_to_include, color_cycle):
        if layer in available_layers:
            layer_gdf = gpd.read_file(gpkg_path, layer=layer)
            # Simplify geometries for performance improvement
            layer_gdf['geometry'] = layer_gdf['geometry'].simplify(tolerance=0.01, preserve_topology=True)
            # Plot the entire layer at once
            layer_gdf.plot(ax=ax, color=color, label=layer if layer not in labeled_layers else None)
            labeled_layers.add(layer)

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


def get_catchments_from_gpkg(gpkg_path: str, layer_name: str = 'divides') -> list[str | int]:
    """
    Extracts a list of catchments from a specified layer in a GeoPackage.

    :param gpkg_path: Path to the GeoPackage file.
    :param layer_name: Name of the layer containing catchments. Defaults to 'divides'.
    :return: List of catchment identifiers (e.g., 'divide_id').
    :raises ValueError: If the specified layer or the 'divide_id' column is missing.
    """
    if gpkg_path:
        # List all layers to verify the catchments layer exists
        available_layers = fiona.listlayers(gpkg_path)
        if layer_name not in available_layers:
            raise ValueError(f"Layer '{layer_name}' not found in the GeoPackage. Available layers: {available_layers}")

        # Read the catchments layer
        gdf = gpd.read_file(gpkg_path, layer=layer_name)

        # Extract the 'divide_id' column
        if 'divide_id' in gdf.columns:
            catchments = gdf['divide_id'].tolist()
        else:
            raise ValueError("The 'divide_id' column was not found in the layer.")

        return catchments
    else:
        return []
