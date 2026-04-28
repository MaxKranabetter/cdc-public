import rasterio

def get_value_at_coordinate(tif_path, x, y):
    try:
        with rasterio.open(tif_path) as src:
            generator = src.sample([(x, y)])
            value = next(generator)
            
        return value
    except Exception as e:
        print(f"Error reading raster value at ({x}, {y}): {e}")
        return None