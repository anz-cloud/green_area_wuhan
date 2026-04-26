import requests
import time
import pandas as pd

# 1. 基础函数：获取单页 POI 数据

def get_poi_page(api_key, keywords, types, city, page=1, citylimit="true"):
    """
    调用高德地图「关键字搜索 API」，获取单页 POI 数据。

    参数：
        api_key  : 高德开放平台 Web 服务 API Key
        keywords : 搜索关键词，例如 "小学|中学|大学"
        types    : POI 分类代码，例如 "141201|141203|141204"
        city     : 城市名称或 adcode，例如 "北京"
        page     : 当前页码，从 1 开始
        citylimit: 是否严格限制在城市范围内，默认 "true"

    返回：
        成功时返回 API 响应的 JSON 数据（字典），失败时返回 None
    """
    base_url = "https://restapi.amap.com/v3/place/text"

    params = {
        "key": api_key,
        "keywords": keywords,
        "types": types,
        "city": city,
        "citylimit": citylimit,
        "offset": "25",          # 每页最多 25 条记录
        "page": str(page),
        "extensions": "all",     # 返回详细信息（包含地址、经纬度等）
        "output": "json"
    }

    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()      # 检查 HTTP 状态码
        data = response.json()

        if data.get("status") == "1":    # 高德返回 status=1 表示成功
            return data
        else:
            print(f"  API 返回错误：{data.get('info', '未知错误')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  网络请求异常：{e}")
        return None



# 2. 核心函数：翻页获取全部学校数据

def fetch_all_schools(api_key, keywords, types, city, citylimit="true"):
    """
    循环翻页，获取指定城市内所有的学校 POI 数据。

    参数：
        api_key, keywords, types, city, citylimit : 同 get_poi_page

    返回：
        包含所有学校信息的列表，每个元素为一个字典。
    """
    all_schools = []
    page = 1

    while True:
        print(f"  正在请求第 {page} 页...", end=" ")

        data = get_poi_page(api_key, keywords, types, city, page, citylimit)

        if data is None:
            print("请求失败，终止翻页。")
            break

        pois = data.get("pois", [])
        print(f"获取到 {len(pois)} 条记录。")

        if not pois:
            print("  已无更多数据。")
            break

        # 解析每条 POI 记录
        for poi in pois:
            # 经纬度字段格式为 "经度,纬度"
            location = poi.get("location", "")
            if location:
                lon_str, lat_str = location.split(",")
                lng = float(lon_str)
                lat = float(lat_str)
            else:
                lng, lat = None, None

            school_info = {
                "name": poi.get("name"),
                "address": poi.get("address"),
                "lng": lng,
                "lat": lat,
                "pname": poi.get("pname"),          # 省份
                "cityname": poi.get("cityname"),    # 城市
                "adname": poi.get("adname"),        # 区/县
            }
            all_schools.append(school_info)

        # 判断是否已获取全部数据
        # 高德返回的 count 字段为总数（但有时不精确），也可通过当前页返回条数 < 25 来判断
        total_count = int(data.get("count", 0))
        if len(all_schools) >= total_count or len(pois) < 25:
            print(f"  数据获取完毕，共计 {len(all_schools)} 条。")
            break

        page += 1
        time.sleep(0.1)   # 短暂延时，避免请求过快被限制

    return all_schools



# 3. 主程序入口

if __name__ == "__main__":
    MY_API_KEY = "3595b317d011dd8480a8deb09252f14c"

    # 配置搜索参数
    CITY_NAME = "武汉"                               # 目标城市
    SEARCH_KEYWORDS = "小学|中学"               # 关键词，支持多词组合
    POI_TYPES = "141204|141203"               # 大学|中学|小学 的分类代码

    print(f"开始获取【{CITY_NAME}】的学校数据...")

    schools = fetch_all_schools(MY_API_KEY, SEARCH_KEYWORDS, POI_TYPES, CITY_NAME)

    if schools:
        # 将列表转换为 pandas DataFrame 并导出为 Excel
        df = pd.DataFrame(schools)
        filename = f"{CITY_NAME}_schools_data.xlsx"
        df.to_excel(filename, index=False, engine="openpyxl")
        print(f"数据已成功保存到文件：{filename}")
        print(f"共计获取 {len(schools)} 所学校。")
    else:
        print("未获取到任何学校数据，请检查 API Key 或网络连接。")
