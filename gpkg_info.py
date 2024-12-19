import argparse
import os

import fiona
import geopandas as gpd

"""
This program is not part of the server, but is a stand-alone utility program for displaying information about gpkg files
"""


def list_layers(gpkg_path: str) -> list[str]:
    """
    List all layers in the GeoPackage file.
    """
    try:
        return fiona.listlayers(gpkg_path)
    except Exception as e:
        raise RuntimeError(f"Failed to list layers in '{gpkg_path}': {e}")


def find_gage_id(gpkg_path: str, layer_name: str = "hydrolocations", field_name: str = "hl_uri") -> list[str]:
    """
    Find and extract the gage_id(s) from the specified layer and field.

    :param gpkg_path: Path to the GeoPackage file.
    :param layer_name: Name of the layer likely containing gage_id. Defaults to 'hydrolocations'.
    :param field_name: Name of the field containing gage_id. Defaults to 'hl_uri'.
    :return: List of unique gage_ids found in the specified layer and field.
    """
    try:
        layers = list_layers(gpkg_path)
        if layer_name not in layers:
            print(f"Layer '{layer_name}' not found in the GeoPackage.")
            return []

        gdf = gpd.read_file(gpkg_path, layer=layer_name)
        if field_name in gdf.columns:
            gage_ids = gdf[field_name].astype(str).unique().tolist()
            print(f"Found gage_id(s) in layer '{layer_name}': {gage_ids}")
            return gage_ids
        else:
            print(f"Field '{field_name}' not found in layer '{layer_name}'.")
            return []
    except Exception as e:
        raise RuntimeError(f"Error while searching for gage_id in layer '{layer_name}': {e}")


def validate_catchments_in_layer(gpkg_path: str, layer_name: str) -> list[str]:
    """
    Validate and extract catchments from the specified layer.
    """
    try:
        gdf = gpd.read_file(gpkg_path, layer=layer_name)

        if 'divide_id' in gdf.columns:
            return gdf['divide_id'].astype(str).tolist()
        else:
            return []
    except Exception as e:
        raise RuntimeError(f"Failed to validate catchments in layer '{layer_name}': {e}")


def find_catchments(gpkg_path: str, target_layers: list[str] = ["divides", "catchments", "watersheds"]) -> None:
    """
    Find and display catchments from the most likely layers.

    :param gpkg_path: Path to the GeoPackage file.
    :param target_layers: List of layer names likely to contain catchments.
    """
    try:
        layers = list_layers(gpkg_path)
        for layer in target_layers:
            if layer in layers:
                print(f"\nChecking for catchments in layer '{layer}':")
                catchments = validate_catchments_in_layer(gpkg_path, layer)
                if catchments:
                    print(f"  Found {len(catchments)} catchments in layer '{layer}'.")
                    print(f"  Catchments: {', '.join(catchments)}")
                    return  # Stop searching once catchments are found
                else:
                    print(f"  No catchments found in layer '{layer}'.")
        print("\nNo catchments found in the specified layers.")
    except Exception as e:
        print(f"Error while searching for catchments: {e}")


def display_layer_metadata(gpkg_path: str, layer_name: str) -> None:
    """
    Display metadata for a specific layer in the GeoPackage.

    :param gpkg_path: Path to the GeoPackage file.
    :param layer_name: Name of the layer to analyze.
    """
    try:
        gdf = gpd.read_file(gpkg_path, layer=layer_name)
        print(f"Layer '{layer_name}' metadata:")
        print(gdf.info())
        print("\nSample data:")
        print(gdf.head())
    except Exception as e:
        raise RuntimeError(f"Failed to read metadata for layer '{layer_name}': {e}")


def main():
    parser = argparse.ArgumentParser(description="GeoPackage Validation Tool")
    parser.add_argument("gpkg_path", type=str, help="Path to the GeoPackage file")
    parser.add_argument("--layer-metadata", type=str, metavar="LAYER_NAME", help="Display metadata for the specified layer")

    args = parser.parse_args()

    if not os.path.exists(args.gpkg_path):
        print(f'File {args.gpkg_path} does not exist.')
        return

    try:
        if args.layer_metadata:
            print(f"Displaying metadata for layer '{args.layer_metadata}'...")
            display_layer_metadata(args.gpkg_path, args.layer_metadata)
        else:
            print("\nSearching for gage_id in the 'hydrolocations' layer:")
            find_gage_id(args.gpkg_path)

            print("\nListing all layers in the GeoPackage:")
            layers = list_layers(args.gpkg_path)
            for layer in layers:
                print(f"- {layer}")

            find_catchments(args.gpkg_path)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
