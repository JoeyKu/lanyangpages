import json
import os
import hashlib
import boto3
from botocore.exceptions import ClientError
import jwt  # <-- 1. 匯入 jwt 函式庫
import datetime # <-- 2. 匯入 datetime 來設定 token 過期時間

# 從環境變數讀取資料表名稱
ACCOUNTS_TABLE_NAME = os.environ.get("ACCOUNTS_TABLE_NAME", "users")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

# ---- 與之前相同的 DynamoDB 連線邏輯 ----
if os.environ.get("AWS_SAM_LOCAL"):
    # 使用你找到的電腦 IP 位址
    dynamodb_endpoint = "http://192.168.200.144:8000"
    print(f"Connecting to local DynamoDB at {dynamodb_endpoint}")
    dynamodb_resource = boto3.resource("dynamodb", endpoint_url=dynamodb_endpoint)
else:
    print("Connecting to AWS DynamoDB")
    dynamodb_resource = boto3.resource("dynamodb")

table = dynamodb_resource.Table(ACCOUNTS_TABLE_NAME)

def lambda_handler(event, context):
    """
    處理登入請求。
    期望的 Body: {"user_id": "some_user", "password": "some_password"}
    """

    print("Login lambda_handler started")
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
    }

    try:
        print(event.get("body"))
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Invalid or missing request body"})}

    user_id = body.get("user_id")
    password = body.get("password")

    # 1. 驗證輸入
    if not user_id or not password:
        return {
            "statusCode": 400, # Bad Request
            "headers": cors_headers,
            "body": json.dumps({"message": "'user_id' and 'password' are required"}),
        }

    # 2. 將傳入的密碼用同樣的 SHA256 演算法加密
    sha256 = hashlib.sha256()
    sha256.update(password.encode('utf-8'))
    calculated_password_hash = sha256.hexdigest()
    
    #sha256 = hashlib.sha256()
    #sha256.update(password.encode('utf-8')) # 需要將 string 編碼成 bytes
    #hashed_password = sha256.hexdigest()   # 取得十六進位的雜湊值

    # 3. 從 DynamoDB 取得使用者資料
    try:
        response = table.get_item(Key={'user_id': user_id})
        item = response.get('Item')

        # 4. 驗證使用者是否存在以及密碼是否相符
        if item and item.get('password') == calculated_password_hash:
            print(f"Login successful for user_id: {user_id}")
            # --- ↓↓↓↓ 登入成功，產生 JWT ↓↓↓↓ ---

            # 4. 建立 JWT 的 payload (酬載)
            payload = {
                'sub': user_id,  # Subject，通常是使用者的唯一標識符
                'iat': datetime.datetime.utcnow(),  # Issued At Time，簽發時間
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=72) # Expiration Time，過期時間 (72 小時後)
            }

            # 5. 使用 PyJWT 產生 token
            if not JWT_SECRET_KEY:
                print("ERROR: JWT_SECRET_KEY environment variable not set.")
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Server configuration error"})}

            token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')

            print(f"Login successful for user_id: {user_id}, token generated.")

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "message": "Login successful",
                    "user_id": user_id,
                    "token": token
                }),
            }
        else:
            # 登入失敗 (帳號不存在或密碼錯誤)
            print(f"Login failed for user_id: {user_id}")
            # 安全性最佳實踐：不要明確告知是「帳號不存在」還是「密碼錯誤」
            return {
                "statusCode": 401, # Unauthorized
                "headers": cors_headers,
                "body": json.dumps({"message": "Invalid user_id or password"}),
            }

    except ClientError as e:
        print(f"DynamoDB Error: {e.response['Error']['Message']}")
        return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "An error occurred during login"})}
