import json
import os
import hashlib  # 用於 SHA256 加密
import boto3
from botocore.exceptions import ClientError
import traceback 

# 從環境變數讀取資料表名稱
ACCOUNTS_TABLE_NAME = "users" #os.environ.get("ACCOUNTS_TABLE_NAME", "users")

# ---- 與之前相同的 DynamoDB 連線邏輯 ----
if os.environ.get("AWS_SAM_LOCAL"):
    dynamodb_endpoint = "http://192.168.200.144:8000"
    print(f"Connecting to local DynamoDB at {dynamodb_endpoint}")
    dynamodb_resource = boto3.resource("dynamodb", endpoint_url=dynamodb_endpoint)
else:
    print("Connecting to AWS DynamoDB")
    dynamodb_resource = boto3.resource("dynamodb")

table = dynamodb_resource.Table(ACCOUNTS_TABLE_NAME)

def lambda_handler(event, context):
    """
    處理帳號建立請求。
    期望的 Body: {"user_id": "some_user", "password": "some_password"}
    """

    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
    }

    # 1. 處理瀏覽器的 OPTIONS 預檢請求
    if event['httpMethod'] == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps('CORS preflight check successful')
        }


    try:
        # API Gateway 會將 POST 的 body 包成一個字串，需要先解析
        print(event)
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Invalid JSON in request body"})}

    user_id = body.get("user_id")
    password = body.get("password")

    # 1. 驗證輸入
    if not user_id or not password:
        return {
            "statusCode": 400, # Bad Request
            "headers": cors_headers,
            "body": json.dumps({"message": "'user_id' and 'password' are required"}),
        }

    # 2. 將密碼用 SHA256 加密
    sha256 = hashlib.sha256()
    sha256.update(password.encode('utf-8')) # 需要將 string 編碼成 bytes
    hashed_password = sha256.hexdigest()   # 取得十六進位的雜湊值


    # 3. 將資料存入 DynamoDB
    try:
        table.put_item(
            Item={
                'user_id': user_id,
                'password': hashed_password,
            },
            # 最佳實踐：使用條件表達式避免覆蓋已存在的帳號
            ConditionExpression="attribute_not_exists(user_id)"
        )
        print(f"Successfully created account: {user_id}")
        return {
            "statusCode": 201, # Created
            "headers": cors_headers,
            "body": json.dumps({
                "message": "Account created successfully",
                "account": user_id
            }),
        }
    except ClientError as e:
        print("--- AN EXCEPTION OCCURRED ---")
        traceback.print_exc()

        # 2. 印出 Boto3 回報的完整錯誤物件
        error_code = e.response.get("Error", {}).get("Code")
        error_message = e.response.get("Error", {}).get("Message")
        print(f"Boto3 ClientError Code: {error_code}")
        print(f"Boto3 ClientError Message: {error_message}")

        # 如果帳號已存在，條件檢查會失敗
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f"Failed to create account. Account '{user_id}' already exists.")
            return {
                "statusCode": 409, # Conflict
                "headers": cors_headers,
                "body": json.dumps({"message": f"Account '{user_id}' already exists"}),
            }
        # 其他 DynamoDB 錯誤
        else:
            print(f"DynamoDB Error: {e.response['Error']['Message']}")
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Error creating account"})}
