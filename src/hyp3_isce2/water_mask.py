"""Create and apply a water body mask"""
import subprocess
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas as gpd
from osgeo import gdal
from pyproj import CRS
from shapely import geometry


from hyp3_isce2.utils import GDALConfigManager

gdal.UseExceptions()


def split_geometry_on_antimeridian(geometry: dict):
    geometry_as_bytes = json.dumps(geometry).encode()
    cmd = ['ogr2ogr', '-wrapdateline', '-datelineoffset', '20', '-f', 'GeoJSON', '/vsistdout/', '/vsistdin/']
    geojson_str = subprocess.run(cmd, input=geometry_as_bytes, stdout=subprocess.PIPE, check=True).stdout
    return json.loads(geojson_str)['features'][0]['geometry']


def create_water_mask(input_image: str, output_image: str, gdal_format='GTiff'):
    """Create a water mask GeoTIFF with the same geometry as a given input GeoTIFF

    The water mask is assembled from GSHHG v2.3.7 Levels 1, 2, 3, and 5 at full resolution. To learn more, visit
    https://www.soest.hawaii.edu/pwessel/gshhg/

    Shoreline data is unbuffered and pixel values of 1 indicate land touches the pixel and 0 indicates there is no
    land in the pixel.

    Args:
        input_image: Path for the input GDAL-compatible image
        output_image: Path for the output image
        gdal_format: GDAL format name to create output image as
    """
    src_ds = gdal.Open(input_image)

    driver_options = []
    if gdal_format == 'GTiff':
        driver_options = ['COMPRESS=LZW', 'TILED=YES', 'NUM_THREADS=ALL_CPUS']

    dst_ds = gdal.GetDriverByName(gdal_format).Create(
        output_image,
        src_ds.RasterXSize,
        src_ds.RasterYSize,
        1,
        gdal.GDT_Byte,
        driver_options,
    )
    dst_ds.SetGeoTransform(src_ds.GetGeoTransform())
    dst_ds.SetProjection(src_ds.GetProjection())
    dst_ds.SetMetadataItem('AREA_OR_POINT', src_ds.GetMetadataItem('AREA_OR_POINT'))

    extent = gdal.Info(input_image, format='json')['wgs84Extent']
    corrected_extent = split_geometry_on_antimeridian(extent)
    extent_gdf = gpd.GeoDataFrame(index=[0], geometry=[geometry.shape(corrected_extent)], crs='EPSG:4326')
    mask_location = '/vsicurl/https://asf-dem-west.s3.amazonaws.com/WATER_MASK/GSHHG/hyp3_water_mask_20220912.shp'

    mask = gpd.read_file(mask_location, mask=corrected_extent)

    mask = mask.clip(extent_gdf)

    with TemporaryDirectory() as temp_dir:
        temp_file = str('mask.shp')
        mask.to_file(temp_file, driver='ESRI Shapefile')
        with GDALConfigManager(OGR_ENABLE_PARTIAL_REPROJECTION='YES'):
            gdal.Rasterize(dst_ds, temp_file, allTouched=True, burnValues=[0])

    del src_ds, dst_ds