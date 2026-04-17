import json
import urllib.request
import urllib.parse
import os

# Original cURL headers from the user
DEFAULT_COOKIE = "RAP_XSRF_TOKEN=AImk1AKX39L0p1Py5ny5G25aIY8p9TYD4A:1776325608755; _ga_S4FJY0X3VX=GS2.1.s1776322951$o1$g1$t1776325611$j1$l0$h0; SIDCC=AKEyXzURPnkHtsNJ5HVx36olUPKyNuK9Kx0zy27YcwyZAOP77rsnbmwSVkvrM2-FsirOCdLTpyo; __Secure-1PSIDCC=AKEyXzUDsaXcRgNUXYzlWZEkCVZyNMFMbLKdunuT7VfWeK2JN-50xo9t1_i3J5agN2kJZe2tOv8; __Secure-3PSIDCC=AKEyXzUGZz9CP0qNIXWucGOSaZcX_g4fLoWRiNiRinYmI4uvEHvZJ1uqvtz_5DP0u5IfyPmPsHI; _ga=GA1.3.542595081.1776322951; _gid=GA1.3.1454291649.1776322951; _gat_marketingTracker=1; _gat=1; NID=530=Vd0QAiBf36Rm08Ik_E7VB40Wu8gWj0mbNNFfc6yR1iQd7j9UwrHyMiPLKdQFzZb6t7oq82_J195NMiujrA6OI_5FTOzYApNzYrKapkiq7y0WbTh7omPLWDCQDVQx6zsO5VycW90kvFg-LWH4YYTDJSJYEquhri0-Tns8d9MPtmjh5XLQZpaAgUZ7AD1E4zJ49I9CeAc-f-JysylECe0x294tdEZmzgoQ-ViNniW_4-1MJU9NvHk6SYQ027lLI40OcBifKgw5QtTphrWs6GA85N0tjlsSso8kOT2mAcO4Vznk8WDfIuqQopbr1U-g2TD8jgk2r7J14X1pvqG1wjGE-urmqAIfYPBbwOiEPRT6O2CD7GedjKRtrOYv2Y5RPLxFgjHZmk5PeMXbBfVMy8HZX6QwfThpYb3wt1mxpfRPAsnQCQcEkHO1gpqFyyb-U-oJEZHs2Y4qEQu-9WMms_8Y1aU12u-y6Im1qIx6mb6Fu-tUwGTiHgoi9OyLgHSaQ6_SAcXZu69YgbHu6XbHFfbazfPcvYwrIr0-g04JOlKHgcswlZTLQimI6afopV0YvF7RvuW5Fl9DAxfOd-raVTo-AliRCZ_XBmwTMIj18QDYc1RUNhNxUpPf6sDzSpFLZNJYR-QSI8x8d_SOj9xdrNy9L8zg0t1N5YeX5ZwM47uO1LQLrP1FyUyQaodW5nBsIYmq8CiHf5tv2aOCfT8r1HryAjQGOH9PtY82HL8AlHWCb6Wz6Np4ddagyuzBe3H4t4OE0YfxBS43Ktgtf7pDFX0C_Vac5BraiRbBDGDnH4Loq4P0SQk1br09jhLlLiFzaOTigvTlCFUgDBqFIawBFuvLfM9Uhbsg-aYHbL2qMyX58avw9mRsOw0tt7TOLhQ49qAsCFyZQNf6aNPY-NlB1Y6lU8bggx1N9GRJ2cQ-5zWDv9csHdO-uYmPlZSjOYaq0514IPrtJeSeBS4vrmqAGX7mRU4BhFAq050ezj2sUWLKaEpdS9hfFhNXMgYAgqogKZSWprCLlTHgr3xLJ53R2Yf936VuCTEXpLpsxe2eKrKwPvrUstzsDv1OnE13cZBDJVEQ7z7pMzZtvhgZAH9c78QZc1HlnZ4ixXNUXAFEZHAHZN4X0fugegnHZswM2gDYXrhxK-dDp6egjoMMQoM3o9a8vidDaCr0SUBg8XXjR_RTrKlNaSG_jRbI5NwFixVPDFWWTZSdUfsmB55qjlKQHb6pXJwSkhd3iboPrE-CyIYn0a3WJV54PBg9ZKfnbBrylniprkoUfQPwAOaXnNNW4Rvk34my6Rho-thULd9_SEs9LhDtHxG6J3fQHjy9Z-Im3_efAzg7_gKZGMoF_N9vPFj_A7ZJd9O6e0rqosjsbIt3B0I0S_HYPbx-irpnK-G_BCJ-RFbhRpjpx0dgCd_gyPC1lLQF7CFtpmpNG_urJEQzHkxbxxry1lvqy6XRYwNYsbSgQjOz7nHn4sRHqpdmJyu2aXVZD-TroLIZ6C-sAeg0qgl4Ef9PxgM4qZlqCbWW7g9xOdjUDtrmm_Np1bNPgArB7kOhrkbojWMiJryhql1DxCTkubGV4jIvsWq8SY02Qns4BESWEXeOtaowk-DrrTGUBTPoTJViIkLgxFHGbVVyjoJTrLGWNZ9NDDuyIOVos5nTODP6O7u4kxvPwqDkMk4RxO0CdIYwlhSfdUWRh1WnNRDa_FQlDeIA23YAQuF4ZUzcUGNK2R23eQiUuRhxXruNbHfEY_MXcfr18cm78NkXT3vjHt1P0HjpxpBH17ZVKq_UPZDeO7l02tv2cN-Eiy_pcGj3vBaU_YZTx2j7VzuPl8JKO6VUIald16ZFb6Qp7ETZB2i-jgadAbq0dMgYLUltdC4_1KTH6GTGKPB0HCektE-aO9Hz4f0d2By1Q4mGCL6Xa0Y6blD3xxy3-UC_KyqBotHo9exEDDtLRdMJESgM2_clO7HvyTfxZ7ZExPfHgVNJbkfizG7iYgkOOueVWD8D8q_jut1FIn-X-t8xa-KIAdxkWEuATup0veHQpKNMkoIOUyjhhtDPvp6aXcy957pwA8NxqhSkIynvsVqeWQ2n4HzFMGRMmbVN5sy2qkcb-b-whb_4h81j0hZEU18jyi8l-KsQ_cPTIgVDrM8IQiNTAXs; __Secure-1PSIDTS=sidts-CjIBWhotCSJVOk7n6arm1vq-amz8Kc_DD9wUt3zOb7EVNIJnBL6al39bGqDx7cEaBUXE0BAA; __Secure-3PSIDTS=sidts-CjIBWhotCSJVOk7n6arm1vq-amz8Kc_DD9wUt3zOb7EVNIJnBL6al39bGqDx7cEaBUXE0BAA; S=billing-ui-v3=4BlPqiJYsmPZWoq-EcpiCybDx2KsK_W8:billing-ui-v3-efe=4BlPqiJYsmPZWoq-EcpiCybDx2KsK_W8; APISID=BHnZiqdLDM9KxXBh/AfWz9rcJWvVd3waN0; HSID=AZVjoEAayA860ykTX; SAPISID=silhwS9jUN67ilz9/AnG96yQgzjj-Ot54_; SID=g.a0008whAMZnNYrxrFa7zrqW0Lz2CtNP7GOxM-H-5p1XduxdRDuukBTONEwISDra28sN4jDj48QACgYKAf0SARUSFQHGX2MiYLM05F0frKbMBc-Z2NiAIRoVAUF8yKpcaJzUhD6xrNtIjDWDCbx20076; SSID=A03XY9pbOcitPYGOD; __Secure-1PAPISID=silhwS9jUN67ilz9/AnG96yQgzjj-Ot54_; __Secure-1PSID=g.a0008whAMZnNYrxrFa7zrqW0Lz2CtNP7GOxM-H-5p1XduxdRDuukLfnZ-DI1MwNfY2kMRRljUgACgYKAVESARUSFQHGX2MiAPxJcvunK-1xK9TMl4Hs5xoVAUF8yKqERuiRQn5WlEca02ggiweQ0076; __Secure-3PAPISID=silhwS9jUN67ilz9/AnG96yQgzjj-Ot54_; __Secure-3PSID=g.a0008whAMZnNYrxrFa7zrqW0Lz2CtNP7GOxM-H-5p1XduxdRDuukhsGlQafFii1_lNtIv7v7OgACgYKAVYSARUSFQHGX2MilzNh3Qc3kgDH4Hwbh-mcuBoVAUF8yKpeoKSrVCbmyKUzm19GnEbA0076; SEARCH_SAMESITE=CgQIzqAB; AEC=AaJma5u6xn17XEU2og2tAKOLYFWUkFbMe4cev5lxC8-H8Sjmd5CeqZ1ngA; OGP=-19050183:-7039716452:-7253362699:; OGPC=19050183-1:7039716452-1:7253362699-1:; __Secure-BUCKET=CJID"
DEFAULT_XSRF = "AImk1AKX39L0p1Py5ny5G25aIY8p9TYD4A:1776325608755"

LOOKER_PAYLOAD = """{"dataRequest":[{"requestContext":{"reportContext":{"reportId":"2a3eaf2b-5c24-47e1-b447-eb33cd2c12bc","pageId":"80267794","mode":1,"componentId":"cd-059c10azwd","displayType":"simple-table"},"requestMode":0},"datasetSpec":{"dataset":[{"datasourceId":"dae10274-330b-4bc8-bd00-66c05707bdec","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_mkwqrne1wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_app_code_"}},{"name":"qt_okwqrne1wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_app_name_"}},{"name":"qt_5ebrhbu5wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_date_"}},{"name":"qt_7osqrne1wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"calc_lubs78d1wd","aggregation":6}},{"name":"qt_781blxx5wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"calc_z7mnf7d1wd","aggregation":6}},{"name":"qt_jepmefq4wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"calc_mh1mq9p4wd","aggregation":6}},{"name":"qt_avn5p0s5wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"calc_sjkirbq4wd","aggregation":6}},{"name":"qt_3gtqrne1wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_admob_revenue_","aggregation":6}},{"name":"qt_bmj97bmexd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_google_spend_","aggregation":6}},{"name":"qt_ggzabcmexd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_mintegral_spend_","aggregation":6}},{"name":"qt_5infecmexd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_tiktok_spend_","aggregation":6}},{"name":"qt_gfttmcmexd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_facebook_spend_","aggregation":6}},{"name":"qt_w0uqrne1wd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_conversion_rate_","aggregation":6}}],"sortData":[{"sortColumn":{"name":"qt_mkwqrne1wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_app_code_"}},"sortDir":1},{"sortColumn":{"name":"qt_5ebrhbu5wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_date_"}},"sortDir":0}],"includeRowsCount":true,"relatedDimensionMask":{"addDisplay":false,"addUniqueId":false,"addLatLong":false},"paginateInfo":{"startRow":1,"rowsCount":250},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":true,"conceptType":0,"concept":{"ns":"t0","name":"qt_ow14wh5j0d"},"filterConditionType":"IN","stringValues":["B081","B087","B098","B117","B097","B122"],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_app_code_"}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"dateRangeDimensions":[{"name":"qt_hcxqrne1wd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_date_"}}],"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"Asia/Saigon"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"cd-059c10azwd_0_0"}}]}"""

def fetch_looker_data():
    cookie = os.environ.get("LOOKER_COOKIE", DEFAULT_COOKIE)
    xsrf_token = os.environ.get("LOOKER_XSRF", DEFAULT_XSRF)

    url = "https://datastudio.google.com/u/1/batchedDataV2?appVersion=20260407_0709"
    headers = {
        "Content-Type": "application/json",
        "Sec-Fetch-Dest": "empty",
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Sec-Fetch-Mode": "cors",
        "Host": "datastudio.google.com",
        "Origin": "https://datastudio.google.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
        "Referer": "https://datastudio.google.com/u/1/reporting/2a3eaf2b-5c24-47e1-b447-eb33cd2c12bc/page/0TxaF",
        "Connection": "keep-alive",
        "Cookie": cookie,
        "X-RAP-XSRF-TOKEN": xsrf_token,
        "Priority": "u=3, i",
        "encoding": "null"
    }

    import requests
    try:
        response = requests.post(url, headers=headers, data=LOOKER_PAYLOAD)
        if response.status_code == 200:
            response_data = response.text
            if response_data.startswith(")]}'"):
                response_data = response_data[4:].strip()
            return json.loads(response_data)
        else:
            print(f"Looker Studio request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching looker data: {e}")
        return None

def parse_looker_data(data):
    if not data or "dataResponse" not in data:
        return []

    try:
        table_dataset = data["dataResponse"][0]["dataSubset"][0]["dataset"]["tableDataset"]
        column_info = table_dataset.get("columnInfo", [])
        columns = table_dataset.get("column", [])
        
        def get_column_values(col):
            if "stringColumn" in col:
                return col["stringColumn"].get("values", [])
            elif "doubleColumn" in col:
                return col["doubleColumn"].get("values", [])
            elif "dateColumn" in col:
                return col["dateColumn"].get("values", [])
            elif "int64Column" in col:
                return col["int64Column"].get("values", [])
            return []

        app_codes = get_column_values(columns[0]) if len(columns) > 0 else []
        app_names = get_column_values(columns[1]) if len(columns) > 1 else []
        dates = get_column_values(columns[2]) if len(columns) > 2 else []
        admob_revs = get_column_values(columns[7]) if len(columns) > 7 else []
        google_spends = get_column_values(columns[8]) if len(columns) > 8 else []
        mintegral_spends = get_column_values(columns[9]) if len(columns) > 9 else []
        tiktok_spends = get_column_values(columns[10]) if len(columns) > 10 else []
        facebook_spends = get_column_values(columns[11]) if len(columns) > 11 else []

        rows_count = len(app_codes)
        
        results = []
        for i in range(rows_count):
            row = {
                "app_code": app_codes[i] if i < len(app_codes) else "",
                "app_name": app_names[i] if i < len(app_names) else "",
                "date": dates[i] if i < len(dates) else "",
                "admob_revenue": admob_revs[i] if i < len(admob_revs) else 0.0,
                "google_spend": google_spends[i] if i < len(google_spends) else 0.0,
                "mintegral_spend": mintegral_spends[i] if i < len(mintegral_spends) else 0.0,
                "tiktok_spend": tiktok_spends[i] if i < len(tiktok_spends) else 0.0,
                "facebook_spend": facebook_spends[i] if i < len(facebook_spends) else 0.0,
            }
            results.append(row)
            
        return results

    except (KeyError, IndexError) as e:
        print(f"Error parsing looker data structural: {e}")
        return []

def get_looker_data_grouped():
    raw_data = fetch_looker_data()
    if not raw_data:
        return {}
    
    parsed = parse_looker_data(raw_data)
    result = {}
    for row in parsed:
        date_str = row['date']
        if not date_str:
            continue
            
        if date_str not in result:
            result[date_str] = {}
        
        app_code = row['app_code'].strip()
        if app_code:
            result[date_str][app_code] = row
            
    return result

if __name__ == "__main__":
    grouped = get_looker_data_grouped()
    print(f"Successfully processed grouped data. Total dates: {len(grouped)}")
    first_date = list(grouped.keys())[0] if grouped else None
    if first_date:
        print(f"Sample apps for {first_date}:")
        for code, data in grouped[first_date].items():
            print(f" - [{code}] {data['app_name']}: Rev=${data['admob_revenue']}, Spends G={data['google_spend']} M={data['mintegral_spend']}")


