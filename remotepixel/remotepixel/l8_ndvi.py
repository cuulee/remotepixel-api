import json
import base64
from io import BytesIO

import numpy as np
from PIL import Image

import rasterio as rio
from rasterio import warp
from rasterio.enums import Resampling

from remotepixel import utils


def point(scene, coord):

    scene_params = utils.landsat_parse_scene_id(scene)
    meta_data = utils.landsat_get_mtl(scene)
    landsat_address = f's3://landsat-pds/{scene_params["key"]}'

    band_address = f'{landsat_address}_B4.TIF'
    with rio.open(band_address) as band:
        lon_srs, lat_srs = warp.transform('EPSG:4326', band.crs, [coord[0]], [coord[1]])
        b4 = list(band.sample([(lon_srs[0], lat_srs[0])]))[0]
        b4 = float(utils.landsat_to_toa(b4, 4, meta_data)[0])

    band_address = f'{landsat_address}_B5.TIF'
    with rio.open(band_address) as band:
        lon_srs, lat_srs = warp.transform('EPSG:4326', band.crs, [coord[0]], [coord[1]])
        b5 = list(band.sample([(lon_srs[0], lat_srs[0])]))[0]
        b5 = float(utils.landsat_to_toa(b5, 5, meta_data)[0])

    if b4 * b5 > 0:
        ratio = (b5 - b4) / (b5 + b4)
    else:
        ratio = 0

    out = {
        'ndvi': ratio,
        'date': scene_params['date'],
        'cloud': float(utils.landsat_mtl_extract(meta_data, 'CLOUD_COVER'))
    }

    return out


def area(scene, bbox):

    max_width = 512
    max_height = 512

    scene_params = utils.landsat_parse_scene_id(scene)
    meta_data = utils.landsat_get_mtl(scene)
    landsat_address = f's3://landsat-pds/{scene_params["key"]}'

    band_address = f'{landsat_address}_B4.TIF'
    with rio.open(band_address) as band:
        crs_bounds = warp.transform_bounds('EPSG:4326', band.crs, *bbox)
        window = band.window(*crs_bounds, boundless=True)

        width =  window.num_cols if window.num_cols < max_width else max_width
        height = window.num_rows if window.num_rows < max_width else max_width

        b4 = band.read(window=window,
            out_shape=(height, width), indexes=1,
            resampling=Resampling.bilinear, boundless=True)

        b4 = utils.landsat_to_toa(b4, 4, meta_data).astype(float)

    band_address = f'{landsat_address}_B5.TIF'
    with rio.open(band_address) as band:
        crs_bounds = warp.transform_bounds('EPSG:4326', band.crs, *bbox)
        window = band.window(*crs_bounds, boundless=True)

        width =  window.num_cols if window.num_cols < max_width else max_width
        height = window.num_rows if window.num_rows < max_width else max_width

        b5 = band.read(window=window,
            out_shape=(height, width), indexes=1,
            resampling=Resampling.bilinear, boundless=True)

        b5 = utils.landsat_to_toa(b5, 4, meta_data).astype(float)

    ratio = np.where( (b5 * b4) > 0, np.nan_to_num((b5 - b4) / (b5 + b4)), -1)
    ratio = np.where(ratio > -1,
        utils.linear_rescale(ratio, in_range=[-1,1], out_range=[0, 255]), 0)

    img = Image.fromarray(ratio).convert('RGB')

    sio = BytesIO()
    img.save(sio, 'jpeg', subsampling=0, quality=100)
    sio.seek(0)

    return base64.b64encode(sio.getvalue()).decode()
