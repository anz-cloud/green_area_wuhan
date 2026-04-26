import pandas as pd
import time
import math
import aie


# 1. 坐标转换：GCJ-02（高德）→ WGS-84（国际标准）

def gcj02_to_wgs84(lng, lat):
    """将 GCJ-02 经纬度转换为 WGS-84 经纬度"""
    a = 6378245.0          # 长半轴
    ee = 0.00669342162296594323  # 扁率

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


def convert_coordinates(df, lng_col='lng', lat_col='lat'):
    """将 DataFrame 中的 GCJ-02 坐标转换为 WGS-84 坐标"""
    wgs84_lng_list = []
    wgs84_lat_list = []
    for _, row in df.iterrows():
        wgs84_lng, wgs84_lat = gcj02_to_wgs84(row[lng_col], row[lat_col])
        wgs84_lng_list.append(wgs84_lng)
        wgs84_lat_list.append(wgs84_lat)
    df['wgs84_lng'] = wgs84_lng_list
    df['wgs84_lat'] = wgs84_lat_list
    return df



# 2. AI Earth 初始化

def init_aie(access_key_id, access_key_secret):
    """使用阿里云 AccessKey 初始化 AI Earth"""
    aie.Authenticate(access_key_id=access_key_id, access_key_secret=access_key_secret)
    aie.Initialize()
    print("AI Earth 初始化成功！")



# 3. 计算单所学校的 NDVI 和绿地面积
def calculate_green_area(lng, lat, radius=500):
    """计算以 (lng, lat) 为中心、radius 为半径的缓冲区内的平均 NDVI 和绿地面积"""
    # 创建缓冲区域
    point = aie.Geometry.Point([lng, lat])
    roi = point.buffer(radius)

    # 加载 Sentinel-2 影像集合
    s2 = aie.ImageCollection('SENTINEL_MSIL2A')

    # 定义 NDVI 计算函数
    def add_ndvi(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return image.addBands(ndvi)

    # 筛选影像：夏季、少云，计算 NDVI 中值
    ndvi_image = s2 \
        .filterBounds(roi) \
        .filterDate('2023-06-01', '2023-08-31') \
        .filter('eo:cloud_cover < 20') \
        .map(add_ndvi) \
        .select('NDVI') \
        .median()

    # 计算区域平均 NDVI
    ndvi_dict = ndvi_image.reduceRegion(
        reducer=aie.Reducer.mean(),
        geometry=roi,
        scale=10
    )
    ndvi_mean = ndvi_dict.get('NDVI', 0)

    # 估算绿地面积：NDVI > 0.2 视为绿地
    green_mask = ndvi_image.gt(0.2)
    pixel_count_dict = green_mask.reduceRegion(
        reducer=aie.Reducer.sum(),
        geometry=roi,
        scale=10
    )
    green_pixel_count = pixel_count_dict.get('NDVI', 0)
    # Sentinel-2 分辨率 10m，每个像素 100 平方米
    green_area = green_pixel_count * 100 if green_pixel_count else 0

    return ndvi_mean, green_area


# 4. 主程序入口

if __name__ == "__main__":
    # ---------- 请修改以下配置 ----------
    MY_ACCESS_KEY_ID = "//"
    MY_ACCESS_KEY_SECRET = "//"
    INPUT_FILE = "武汉_schools_data.xlsx"      # 你的学校坐标文件
    OUTPUT_FILE = "学校绿地面积计算结果.xlsx"   # 输出结果文件
    # -----------------------------------

    # 读取数据并转换坐标
    print("正在读取学校数据并转换坐标...")
    df = pd.read_excel(INPUT_FILE)
    df = convert_coordinates(df)

    # 初始化 AI Earth
    init_aie(MY_ACCESS_KEY_ID, MY_ACCESS_KEY_SECRET)

    # 批量处理
    results = []
    total = len(df)
    for idx, row in df.iterrows():
        school_name = row['name']
        print(f"正在处理 [{idx+1}/{total}]: {school_name}")
        try:
            ndvi_mean, green_area = calculate_green_area(row['wgs84_lng'], row['wgs84_lat'])
            results.append({
                '学校名称': school_name,
                '地址': row['address'],
                '经度(WGS84)': row['wgs84_lng'],
                '纬度(WGS84)': row['wgs84_lat'],
                '平均NDVI': ndvi_mean,
                '绿地面积(平方米)': green_area
            })
        except Exception as e:
            print(f"  处理失败: {e}")
            results.append({
                '学校名称': school_name,
                '地址': row['address'],
                '经度(WGS84)': row['wgs84_lng'],
                '纬度(WGS84)': row['wgs84_lat'],
                '平均NDVI': None,
                '绿地面积(平方米)': None,
                '错误信息': str(e)
            })
        time.sleep(0.5)  # 避免请求过快

    # 保存结果
    result_df = pd.DataFrame(results)
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"处理完成！结果已保存至 {OUTPUT_FILE}")