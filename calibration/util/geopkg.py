from io import BytesIO
from itertools import cycle

import fiona
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
from shapely.geometry import shape, Polygon, MultiPolygon, MultiLineString

# See https://stackoverflow.com/questions/27147300/matplotlib-tcl-asyncdelete-async-handler-deleted-by-the-wrong-thread
matplotlib.use('Agg')  # Use a backend that doesn't require a display (like for generating images)


def gpkg_to_png(gpkg_path, png_path, layer=None):
    # Read the GeoPackage file
    if layer:
        gdf = gpd.read_file(gpkg_path, layer=layer)
    else:
        gdf = gpd.read_file(gpkg_path)

    # Plot the GeoDataFrame
    fig, ax = plt.subplots(1, 1, figsize=(15, 15))
    gdf.plot(ax=ax, cmap='viridis')

    # Remove axes for better visualization
    ax.set_axis_off()

    # Save the plot as a PNG file
    plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    plt.close()


def gpkg_to_png_selected_layers(gpkg_path, layers_to_include=None):
    if layers_to_include is None:
        layers_to_include = ['nexus', 'flowpaths', 'flowlines']  # Default layers to include

    # Initialize the plot
    fig, ax = plt.subplots(1, 1, figsize=(15, 15))

    # Track which layers have been labeled
    labeled_layers = set()

    # Plot the divides layer (outline) if it exists
    if 'divides' in fiona.listlayers(gpkg_path):
        with fiona.open(gpkg_path, layer='divides') as layer:
            for feature in layer:
                geom = shape(feature['geometry'])
                label = 'divides' if 'divides' not in labeled_layers else None
                if isinstance(geom, Polygon):
                    x, y = geom.exterior.xy
                    ax.plot(x, y, color='black', label=label)
                elif isinstance(geom, MultiPolygon):
                    for poly in geom.geoms:
                        x, y = poly.exterior.xy
                        ax.plot(x, y, color='black', label=label)
                labeled_layers.add('divides')

    # Define a cycle of color maps for the layers
    color_maps = cycle(['blue', 'green', 'red', 'cyan', 'magenta'])

    # Plot each layer if it exists in the file
    available_layers = fiona.listlayers(gpkg_path)

    # Plot each requested layer if it exists
    for layer, color in zip(layers_to_include, color_maps):
        if layer in available_layers:
            with fiona.open(gpkg_path, layer=layer) as lyr:
                for feature in lyr:
                    geom = shape(feature['geometry'])
                    label = layer if layer not in labeled_layers else None
                    if geom.is_valid and geom.geom_type in ['LineString', 'MultiLineString']:
                        if isinstance(geom, MultiLineString):
                            for line in geom.geoms:
                                x, y = line.xy
                                ax.plot(x, y, label=label, color=color)
                        else:
                            x, y = geom.xy
                            ax.plot(x, y, label=label, color=color)
                    labeled_layers.add(layer)

    # Add a legend explicitly
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc='upper right')

    # Remove axes for better visualization
    ax.set_axis_off()



    # Save the plot as a PNG file
    # plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    # plt.close()

    # Convert in memory
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close()
    img_buffer.seek(0)
    return img_buffer
