from io import BytesIO

import geopandas as gpd
import matplotlib.pyplot as plt
import fiona
from itertools import cycle
from shapely.geometry import shape, Polygon, MultiPolygon


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
        layers_to_include = ['nexus', 'flowpaths']

    # Initialize the plot
    fig, ax = plt.subplots(1, 1, figsize=(15, 15))

    # Plot the divides layer (outline)
    with fiona.open(gpkg_path, layer='divides') as layer:
        for feature in layer:
            geom = shape(feature['geometry'])
            if isinstance(geom, Polygon):
                exterior = geom.exterior
                x, y = exterior.xy
                ax.plot(x, y, color='black')
            elif isinstance(geom, MultiPolygon):
                for poly in geom.geoms:
                    exterior = poly.exterior
                    x, y = exterior.xy
                    ax.plot(x, y, color='black')

    # Define a cycle of color maps for the layers
    color_maps = cycle(['viridis', 'plasma', 'inferno', 'magma', 'cividis'])

    # Plot each layer with a different color map
    for layer, cmap in zip(layers_to_include, color_maps):
        gdf = gpd.read_file(gpkg_path, layer=layer)
        if 'geometry' in gdf.columns and not gdf.empty and gdf.geometry.notnull().all():
            gdf.plot(ax=ax, cmap=cmap, label=layer)

    # Remove axes for better visualization
    ax.set_axis_off()

    # Add a legend with layer names
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, layers_to_include + ['divides'], loc='upper right')

    # Save the plot as a PNG file
    # plt.savefig(png_path, bbox_inches='tight', pad_inches=0.1)
    # plt.close()

    # Convert in memory
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close()
    img_buffer.seek(0)
    return img_buffer

