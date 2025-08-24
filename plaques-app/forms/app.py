# form/app.py
import json
import os
import boto3
import jwt
from botocore.exceptions import ClientError

import io
import base64 # <--- 引入 base64 函式庫
from datetime import datetime
import math
from PyPDF2 import PdfWriter, PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# +++ 輔助函式 (維持不變) +++
def draw_multiline_string(canvas, x, y, text, line_height=14):
    lines = text.split('\n')
    for line in lines:
        canvas.drawString(x, y, line)
        y -= line_height

def split_string_if_long(text: str, max_length: int) -> str:
    if not isinstance(text, str) or len(text) <= max_length:
        return text if text is not None else ""
    split_pos = text.rfind(' ', 0, max_length)
    if split_pos != -1:
        first_line = text[:split_pos]
        second_line = text[split_pos+1:]
        return f"{first_line}\n{second_line}"
    else:
        first_line = text[:max_length]
        second_line = text[max_length:]
        return f"{first_line}\n{second_line}"

def create_overlay_for_page(page_records, common_data, base_coordinates):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    # 假設字型檔和此腳本在同一個資料夾
    font_path = "NotoSansTC-VariableFont_wght.ttf" 
    try:
        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
        c.setFont('ChineseFont', 12)
    except Exception as e:
        print(f"錯誤：無法載入字體 {font_path}。錯誤訊息: {e}")
    for field, text in common_data.items():
        if field in base_coordinates and text is not None:
            x, y = base_coordinates[field]
            draw_multiline_string(c, x, y, text)
    x_稱謂, x_項目, x_陽上眷屬 = 90, 135, 327
    start_y, column_gap = 235, 30
    string_max_len = 20
    for index, record in enumerate(page_records):
        current_base_y = start_y - (column_gap * index)
        稱謂 = record.get("稱謂", "")
        項目 = split_string_if_long(record.get("項目", ""), string_max_len)
        陽上眷屬 = record.get("陽上眷屬", "")
        y_adjust_項目 = 5 if "\n" in 項目 else 0
        y_adjust_陽上眷屬 = 5 if "\n" in 陽上眷屬 else 0
        draw_multiline_string(c, x_稱謂, current_base_y, 稱謂)
        draw_multiline_string(c, x_項目, current_base_y + y_adjust_項目, 項目)
        draw_multiline_string(c, x_陽上眷屬, current_base_y + y_adjust_陽上眷屬, 陽上眷屬)
    c.save()
    packet.seek(0)
    return PdfReader(packet)

def add_pages_to_writer(writer, template_page, all_records, common_data, base_coordinates):
    ITEMS_PER_PAGE = 5
    total_records = len(all_records)
    if not total_records: return
    total_pages = math.ceil(total_records / ITEMS_PER_PAGE)
    print(f"正在為此類型新增 {total_pages} 頁...")
    for i in range(0, total_records, ITEMS_PER_PAGE):
        page_records = all_records[i : i + ITEMS_PER_PAGE]
        overlay_pdf = create_overlay_for_page(page_records, common_data, base_coordinates)
        overlay_page = overlay_pdf.pages[0]
        temp_writer = PdfWriter()
        temp_writer.add_page(template_page)
        temp_buffer = io.BytesIO()
        temp_writer.write(temp_buffer)
        temp_buffer.seek(0)
        page_to_merge = PdfReader(temp_buffer).pages[0]
        page_to_merge.merge_page(overlay_page)
        writer.add_page(page_to_merge)


def lambda_handler(event, context):
    """
    此 Lambda 函數的職責是根據提供的 ID (timestamp) 從 plaques 資料表中
    取得單一項目的完整資料，以供表單或其他用途使用。
    支援的端點:
    - GET /forms/{id}: 根據 JWT 的 user_id 和路徑中的 id 取得資料。
    """

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    # ---- DynamoDB 連線邏輯 ----
    if os.environ.get("AWS_SAM_LOCAL"):
        dynamodb_endpoint = "http://192.168.200.144:8000" # <-- 請換成你自己的 IP
        dynamodb_resource = boto3.resource("dynamodb", endpoint_url=dynamodb_endpoint)
        PLAQUES_TABLE_NAME = "plaques" # 直接使用您在 YAML 中定義的實體名稱
        METADATA_TABLE_NAME = "metadata"
    else:
        PLAQUES_TABLE_NAME = os.environ.get("PLAQUE_TABLE_NAME")
        METADATA_TABLE_NAME = os.environ.get("METADATA_TABLE_NAME")
        dynamodb_resource = boto3.resource("dynamodb")

    plaque_table = dynamodb_resource.Table(PLAQUES_TABLE_NAME)
    form_table = dynamodb_resource.Table(METADATA_TABLE_NAME)

    # ---- CORS 標頭設定 ----
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS' # 此函數只支援 GET 和 OPTIONS
    }

    # 1. (安全性) 驗證 JWT Token (這段邏輯與 plaque 函數完全相同)
    try:
        auth_header = event['headers'].get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Missing or invalid token"})}
        
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 從 token 中取得已驗證的使用者帳號
        user_id = payload['sub']

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Token is invalid or has expired"})}
    except Exception:
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Unauthorized"})}


    http_method = event.get('httpMethod')
    
    # ===================================================================
    # --- 處理 GET 請求 (查詢單一項目) ---
    # ===================================================================
    if http_method == 'GET':
        path_params = event.get('pathParameters')
        
        # 檢查路徑參數是否存在且包含 'id'
        if not path_params or 'id' not in path_params:
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"message": "Missing form ID in the path. e.g., /form/{id}"})
            }
        
        form_id = path_params['id'] # 'id' 就是 timestamp
        print(f"Fetching form data with id: {form_id} for user: {user_id}")
        
        try:
            # 使用 get_item 取得特定項目，需要完整的 Primary Key (user_id + timestamp)
            response = plaque_table.get_item(
                Key={
                    'user_id': user_id,
                    'timestamp': form_id
                }
            )
            
            data = response.get('Item')

            # --- 2. 準備資料 (與原本的 __main__ 區塊相同) ---
            formatted_date = datetime.now().strftime("%Y年 %m月 %d日")
            common_page_info = {
                "聯絡人": data['user_name'], "通訊地址": data['user_address'],
                "手機": data['user_phone'], "法會": "孝道月",
                "日期": formatted_date, "牌位": "V"
            }

            grouped_plaques = { "大": [], "中": [], "小": [] }
            for i in data['plaque_data']:
                plaque_type = i.get('type')
                item_name = i.get('item_name') if i.get('item_name') is not None else ""
                t, n = i.get('item_title'), item_name
                if t == '歷代祖先': t, n = '', item_name + ' 氏歷代祖先'
                if t in ['十方法界一切眾生', '未出世子女', '累劫冤親債主']: n, t = t, ''
                record = {"稱謂": t, "項目": n, "陽上眷屬": i.get('item_benefactor')}
                if plaque_type in grouped_plaques: grouped_plaques[plaque_type].append(record)

            base_field_coordinates = {
                "聯絡人": (140, 347), "通訊地址": (150, 290), "手機": (450, 290),
                "日期": (465, 40), "牌位": (0, 0),
            }

            response = form_table.get_item(Key={'meta_id': 'form_normal'})
            item = response.get('Item')
            if not item:
                return {
                    'statusCode': 404,
                    'headers': cors_headers,
                    'body': json.dumps({'error': f'Item with ID {item_id} not found.'})
                }

            # --- 3. 取得 Base64 編碼的資料和檔案類型 ---
            # 假設 Base64 資料儲存在 'file_base64' 欄位
            # 檔案的 MIME 類型儲存在 'file_mime_type' 欄位 (例如 'application/pdf', 'image/png')
            # 檔案的原始名稱儲存在 'file_name' 欄位
            file_base64 = item.get('meta_content')
            mime_type = item.get('file_mime_type', 'application/pdf') 
            #application/octet-stream') # 提供預設值
            file_name = item.get('file_name', 'download') # 提供預設檔名

            if not file_base64:
                return {
                    'statusCode': 404,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Base64 file data not found in the item.'})
                }
                
            # --- 4. 將 Base64 解碼為二進位資料 ---
            try:
                binary_data = base64.b64decode(file_base64)
                original_pdf_stream = io.BytesIO(binary_data)
                original_pdf = PdfReader(original_pdf_stream)
                template_page = original_pdf.pages[0]

                final_writer = PdfWriter()

                # --- 4. 執行核心邏輯，將頁面加入 writer (與原本的 __main__ 區塊相同) ---
                for plaque_type, records in grouped_plaques.items():
                    if not records: continue
                    print(f"--- 開始處理 '{plaque_type}' 牌位 (共 {len(records)} 筆) ---")
                    tablet_y = 93
                    if plaque_type == "小": tablet_y = 195
                    elif plaque_type == "中": tablet_y = 145
                    current_coordinates = base_field_coordinates.copy()
                    current_coordinates["牌位"] = (tablet_y, 40)
                    add_pages_to_writer(final_writer, template_page, records, common_page_info, current_coordinates)

                # --- 5. 將最終的 PDF 寫入記憶體中 ---
                print("正在將 PDF 寫入記憶體...")
                output_stream = io.BytesIO()
                final_writer.write(output_stream)
                
                # 移動到串流的開頭，準備讀取其內容
                output_stream.seek(0)
                pdf_bytes = output_stream.getvalue()

                # --- 6. 準備回傳給 API Gateway 的格式 ---
                print("正在準備回傳的回應...")
                new_headers = cors_headers
                new_headers['Content-Type'] = mime_type
                new_headers['Content-Disposition'] = f'attachment; filename="{file_name}"' # 這會觸發瀏覽器下載
                return {
                    "statusCode": 200,
                    'headers': new_headers,
                    # 將二進位內容進行 Base64 編碼，並轉成字串
                    "body": base64.b64encode(pdf_bytes).decode('utf-8'),
                    # 必須設定為 True，API Gateway 才會在回傳時自動解碼
                    "isBase64Encoded": True
                }

                print(f"Successfully decoded {len(binary_data)} bytes of binary data.")
            except (TypeError, base64.binascii.Error) as e:
                print(f"Base64 decoding error: {e}")
                return {
                    'statusCode': 500,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'Failed to decode Base64 data.'})
                }

            

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'An internal server error occurred.'})
            }
        except ClientError as e:
            print(f"DynamoDB GET item for form Error: {e.response['Error']['Message']}")
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to retrieve form data"})}

    # ===================================================================
    # --- 處理其他不支持的方法 ---
    # ===================================================================
    else:
        return {"statusCode": 405, "headers": cors_headers, "body": json.dumps({"message": "Method not allowed"})}
