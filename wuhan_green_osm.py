import pandas as pd
import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point
import math
import time
import pyproj


# 1. 坐标转换：GCJ-02 → WGS-84
def gcj02_to_wgs84(lng, lat):
    a = 6378245.0
    ee = 0.00669342162296594323

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    def transform_lng(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
        return ret

    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    wgs_lat = lat - dlat
    wgs_lng = lng - dlng
    return wgs_lng, wgs_lat



# 2. 单所学校绿地面积计算函数
def get_utm_crs(lng, lat):
    """根据经纬度自动获取对应的 WGS84 UTM 投影 EPSG 代码"""
    utm_band = int((lng + 180) // 6) + 1
    if lat >= 0:
        epsg = 32600 + utm_band
    else:
        epsg = 32700 + utm_band
    return f"EPSG:{epsg}"

def calculate_green_area_osm(lat, lng, radius=500):
    """
    输入：WGS-84 经纬度、半径（米）
    输出：该缓冲区内的绿地面积（平方米）
    """
    # 创建点
    center_point = Point(lng, lat)
    center_gdf = gpd.GeoDataFrame(geometry=[center_point], crs="EPSG:4326")

    # 获取当地 UTM 投影并转换
    utm_crs = get_utm_crs(lng, lat)
    center_proj = center_gdf.to_crs(utm_crs)

    # 创建缓冲区（单位：米）
    buffer_proj = center_proj.buffer(radius)

    # 将缓冲区转回 WGS84 以便裁剪 OSM 数据
    buffer_wgs84 = buffer_proj.to_crs("EPSG:4326")

    # 定义绿地标签
    green_tags = {
        'leisure': ['park', 'garden', 'nature_reserve', 'playground'],
        'landuse': ['grass', 'forest', 'meadow', 'village_green', 'recreation_ground', 'allotments'],
        'natural': ['wood', 'scrub', 'heath', 'grassland']
    }

    # 下载 OSM 数据
    try:
        green_gdf = ox.features_from_point((lat, lng), tags=green_tags, dist=radius)
    except Exception:
        return 0.0

    if green_gdf.empty:
        return 0.0

    # 裁剪到缓冲区内
    buffer_geom = buffer_wgs84.iloc[0]
    green_gdf = green_gdf[green_gdf.geometry.intersects(buffer_geom)].copy()
    green_gdf['geometry'] = green_gdf.geometry.intersection(buffer_geom)

    # 投影到平面坐标系计算面积（平方米）
    green_proj = green_gdf.to_crs(utm_crs)
    green_proj['area_m2'] = green_proj.geometry.area
    return green_proj['area_m2'].sum()

if __name__ == "__main__":
    
    INPUT_FILE = "武汉_schools_data.xlsx"      # 你的武汉学校数据文件
    OUTPUT_FILE = "武汉中小学绿地面积计算结果.xlsx"

    print("正在读取学校数据...")
    df = pd.read_excel(INPUT_FILE)

    # 检查是否已有 WGS-84 坐标列，如果没有则转换
    if 'wgs84_lng' not in df.columns or 'wgs84_lat' not in df.columns:
        print("开始坐标转换（GCJ-02 → WGS-84）...")
        wgs_lngs, wgs_lats = [], []
        for _, row in df.iterrows():
            wlng, wlat = gcj02_to_wgs84(row['lng'], row['lat'])
            wgs_lngs.append(wlng)
            wgs_lats.append(wlat)
        df['wgs84_lng'] = wgs_lngs
        df['wgs84_lat'] = wgs_lats
        print("坐标转换完成。")
    else:
        print("已有 WGS-84 坐标，跳过转换。")

    results = []
    total = len(df)
    for idx, row in df.iterrows():
        name = row['name']
        print(f"正在处理 [{idx+1}/{total}]: {name}")
        green_area = calculate_green_area_osm(row['wgs84_lat'], row['wgs84_lng'], radius=500)
        results.append({
            '学校名称': name,
            '地址': row.get('address', ''),
            '经度(WGS-84)': row['wgs84_lng'],
            '纬度(WGS-84)': row['wgs84_lat'],
            '绿地面积(平方米)': round(green_area, 2)
        })
        # 礼貌性延时，避免 OSM 服务器过载
        time.sleep(1.5)

    # 导出结果
    result_df = pd.DataFrame(results)
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"\n处理完成！结果已保存到 {OUTPUT_FILE}")
