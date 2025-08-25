# form/app.py
import base64
import io
import json
import os
from datetime import datetime
import math

import boto3
import jwt
from botocore.exceptions import ClientError
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ===================================================================
# --- 組態與常數設定 (Configuration and Constants) ---
# ===================================================================
# 靜態設定值，方便統一管理
PDF_COORDINATES = {
    "聯絡人": (140, 347), "通訊地址": (150, 290), "手機": (450, 290),
    "日期": (465, 40), "牌位": (0, 0),  # 牌位 Y 座標是動態計算的
}
ITEMS_PER_PAGE = 5
STRING_MAX_LENGTH = 20
IS_LOCAL = os.environ.get("AWS_SAM_LOCAL")


# ===================================================================
# --- AWS 資源初始化 (AWS Resource Initialization) ---
# ===================================================================
# 將初始化放在 handler 外部，以便 Lambda 重複使用連線
PLAQUES_TABLE_NAME = os.environ.get("PLAQUE_TABLE_NAME")
METADATA_TABLE_NAME = os.environ.get("METADATA_TABLE_NAME")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

if IS_LOCAL:
    print("偵測到本地 SAM 環境，正在使用本地設定。")
    DYNAMODB_RESOURCE = boto3.resource("dynamodb", endpoint_url="http://192.168.200.144:8000")
else:
    print("正在使用雲端部署設定。")
    DYNAMODB_RESOURCE = boto3.resource("dynamodb")


PLAQUES_TABLE = DYNAMODB_RESOURCE.Table(PLAQUES_TABLE_NAME)
METADATA_TABLE = DYNAMODB_RESOURCE.Table(METADATA_TABLE_NAME)


# ===================================================================
# --- PDF 生成工具函式 (PDF Generation Utilities) ---
# ===================================================================
def draw_multiline_string(canvas_obj, x, y, text, line_height=14):
    """在畫布上繪製可換行的文字。"""
    lines = text.split('\n')
    for line in lines:
        canvas_obj.drawString(x, y, line)
        y -= line_height

def split_string_if_long(text: str, max_length: int) -> str:
    """如果字串過長，則智慧換行。"""
    if not isinstance(text, str) or len(text) <= max_length:
        return text if text is not None else ""
    split_pos = text.rfind(' ', 0, max_length)
    if split_pos != -1:
        return f"{text[:split_pos]}\n{text[split_pos+1:]}"
    return f"{text[:max_length]}\n{text[max_length:]}"

def create_page_overlay(page_records, common_data, coordinates):
    """為單一頁面的資料建立 PDF 疊加層。"""
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    font_path = os.path.join(os.path.dirname(__file__), 'NotoSansTC-VariableFont_wght.ttf')
    #font_path = "NotoSansTC-VariableFont_wght.ttf"
    try:
        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
        c.setFont('ChineseFont', 12)
    except Exception as e:
        print(f"字體載入錯誤: {e}")

    for field, text in common_data.items():
        if field in coordinates and text is not None:
            x, y = coordinates[field]
            draw_multiline_string(c, x, y, text)

    x_稱謂, x_項目, x_陽上眷屬 = 90, 135, 327
    start_y, column_gap = 235, 30
    for index, record in enumerate(page_records):
        current_base_y = start_y - (column_gap * index)
        稱謂 = record.get("稱謂", "")
        項目 = split_string_if_long(record.get("項目", ""), STRING_MAX_LENGTH)
        陽上眷屬 = record.get("陽上眷屬", "")
        y_adjust_項目 = 5 if "\n" in 項目 else 0
        y_adjust_陽上眷屬 = 5 if "\n" in 陽上眷屬 else 0
        draw_multiline_string(c, x_稱謂, current_base_y, 稱謂)
        draw_multiline_string(c, x_項目, current_base_y + y_adjust_項目, 項目)
        draw_multiline_string(c, x_陽上眷屬, current_base_y + y_adjust_陽上眷屬, 陽上眷屬)
    
    c.save()
    packet.seek(0)
    return PdfReader(packet)

def generate_pdf_binary(template_bytes, common_info, grouped_plaques):
    """核心函式：使用範本和資料來生成最終的 PDF 二進位內容。"""
    template_stream = io.BytesIO(template_bytes)
    final_writer = PdfWriter()

    for plaque_type, records in grouped_plaques.items():
        if not records:
            continue
        
        print(f"--- 正在處理 '{plaque_type}' 牌位 (共 {len(records)} 筆) ---")
        
        tablet_y = 93
        if plaque_type == "小": tablet_y = 195
        elif plaque_type == "中": tablet_y = 145
        
        current_coordinates = PDF_COORDINATES.copy()
        current_coordinates["牌位"] = (tablet_y, 40)
       
        total_records = len(records)
        try:
            for i in range(0, total_records, ITEMS_PER_PAGE):
                page_records = records[i : i + ITEMS_PER_PAGE]
                overlay_pdf = create_page_overlay(page_records, common_info, current_coordinates)
                template_stream.seek(0) # 重置串流指標
                page_to_merge = PdfReader(template_stream).pages[0]
                page_to_merge.merge_page(overlay_pdf.pages[0])
                final_writer.add_page(page_to_merge)
        except Exception as e:
            print(f"發生未預期的錯誤: {e}")
            import traceback
            traceback.print_exc()

    output_stream = io.BytesIO()
    final_writer.write(output_stream)
    return output_stream.getvalue()

# ===================================================================
# --- 資料處理與準備函式 (Data Processing and Preparation) ---
# ===================================================================
def prepare_pdf_data(plaque_data):
    """將從 DynamoDB 取得的原始資料轉換為 PDF 生成所需的格式。"""
    common_page_info = {
        "聯絡人": plaque_data.get('user_name'),
        "通訊地址": plaque_data.get('user_address'),
        "手機": plaque_data.get('user_phone'),
        "法會": "孝道月",
        "日期": datetime.now().strftime("%Y年 %m月 %d日"),
        "牌位": "V"
    }
    grouped_plaques = {"大": [], "中": [], "小": []}
    for item in plaque_data.get('plaque_data', []):
        plaque_type = item.get('type')
        item_name = item.get('item_name') if item.get('item_name') is not None else ""
        title, name = item.get('item_title'), item_name
        
        if title == '歷代祖先': title, name = '', f"{item_name} 氏歷代祖先"
        if title in ['十方法界一切眾生', '未出世子女', '累劫冤親債主']: name, title = title, ''
            
        record = {"稱謂": title, "項目": name, "陽上眷屬": item.get('item_benefactor')}
        if plaque_type in grouped_plaques:
            grouped_plaques[plaque_type].append(record)
            
    return common_page_info, grouped_plaques

# ===================================================================
# --- 主處理函式 (Main Handler) ---
# ===================================================================
def lambda_handler(event, context):
    """API Gateway 進入點，處理 GET /forms/{id} 請求。"""
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Content-Disposition, Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }

    try:
        auth_header = event['headers'].get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Missing or invalid token"})}
        
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        user_id = payload['sub']

        if event.get('httpMethod') == 'GET':
            form_id = event.get('pathParameters', {}).get('id')
            if not form_id:
                return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Missing form ID in path"})}

            print(f"正在為使用者 '{user_id}' 取得表單資料 '{form_id}'")
            plaque_response = PLAQUES_TABLE.get_item(Key={'user_id': user_id, 'timestamp': form_id})
            plaque_data = plaque_response.get('Item')
            if not plaque_data:
                return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": "Form data not found"})}

            template_response = METADATA_TABLE.get_item(Key={'meta_id': 'form_normal'})
            template_item = template_response.get('Item')
            if not template_item or 'meta_content' not in template_item:
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Server error: PDF template not found"})}
            
            template_bytes = base64.b64decode(template_item['meta_content'])
            common_info, grouped_plaques = prepare_pdf_data(plaque_data)
            pdf_bytes = generate_pdf_binary(template_bytes, common_info, grouped_plaques)
            
            response_headers = cors_headers.copy()
            response_headers['Content-Type'] = 'application/pdf'
            file_name = "haha"
            response_headers['Content-Disposition']: f"attachment; filename=\"{file_name}\""
            #response_headers['Content-Disposition'] = 'attachment; filename="form.pdf"'
            return {
                "statusCode": 200, "headers": response_headers,
                "body": base64.b64encode(pdf_bytes).decode('utf-8'),
                "isBase64Encoded": True
            }
        else:
            return {"statusCode": 405, "headers": cors_headers, "body": json.dumps({"message": "Method not allowed"})}

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Token is invalid or has expired"})}
    except ClientError as e:
        print(f"DynamoDB 錯誤: {e.response['Error']['Message']}")
        return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to access database"})}
    except (TypeError, base64.binascii.Error) as e:
        print(f"Base64 解碼錯誤: {e}")
        return {'statusCode': 500, 'headers': cors_headers, 'body': json.dumps({'error': 'Failed to decode template file data.'})}
    except Exception as e:
        print(f"發生未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        return {'statusCode': 500, 'headers': cors_headers, 'body': json.dumps({'error': 'An internal server error occurred.'})}
