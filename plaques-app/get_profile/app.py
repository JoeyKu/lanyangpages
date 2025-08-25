# get_profile/app.py
import json
import os
import jwt

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

def lambda_handler(event, context):
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
    }

    try:
        # 1. 從請求標頭 (header) 取得 token
        auth_header = event['headers'].get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Missing or invalid token"})}
        
        token = auth_header.split(" ")[1]

        # 2. 解碼並驗證 token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 從 payload 中取得使用者資訊
        user_account = payload['sub']

        # 3. 回傳受保護的資源
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({
                "message": f"Welcome, you have access to protected data!",
                "account": user_account
            })
        }

    except jwt.ExpiredSignatureError:
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Token has expired"})}
    except jwt.InvalidTokenError:
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Invalid token"})}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Internal server error"})}
