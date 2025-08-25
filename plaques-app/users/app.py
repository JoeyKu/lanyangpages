import json
import os
import hashlib
import boto3
from botocore.exceptions import ClientError
import traceback
import jwt  # <--- 1. 匯入 PyJWT 函式庫

# --- 從環境變數讀取設定 ---
ACCOUNTS_TABLE_NAME = os.environ.get("ACCOUNTS_TABLE_NAME", "users")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# 檢查必要的環境變數是否存在
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable not set.")

# --- DynamoDB 連線邏輯 (與之前相同) ---
if os.environ.get("AWS_SAM_LOCAL"):
    dynamodb_resource = boto3.resource("dynamodb", endpoint_url="http://192.168.200.144:8000")
else:
    dynamodb_resource = boto3.resource("dynamodb")
table = dynamodb_resource.Table(ACCOUNTS_TABLE_NAME)

# --- 輔助函式：解析 JWT 並取得 user_id ---
class TokenError(Exception):
    """自訂的 Token 相關錯誤"""
    pass

def _get_user_id_from_token(event):
    """
    從 event 的 Authorization 標頭中解析 JWT 並回傳 user_id。
    如果失敗則會引發 TokenError。
    """
    try:
        auth_header = event.get('headers', {}).get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise TokenError('Missing or invalid Authorization header')
        
        # 提取 Token 字串 (去掉 "Bearer ")
        token = auth_header.split(" ")[1]
        
        # 解碼並驗證 Token
        # 'sub' (subject) 是 JWT 中儲存使用者 ID 的標準欄位
        decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = decoded_token.get('sub')
        
        if not user_id:
            raise TokenError('Token does not contain a user ID (sub)')
            
        print(f"Token validated for user_id: {user_id}")
        return user_id

    except jwt.ExpiredSignatureError:
        raise TokenError('Token has expired')
    except jwt.InvalidTokenError as e:
        print(f"Invalid Token Error: {e}")
        raise TokenError('Invalid token')
    except Exception as e:
        print(f"An unexpected error occurred during token parsing: {e}")
        raise TokenError('Could not parse token')

# --- 主處理函式 ---
def lambda_handler(event, context):
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT'
    }

    if event['httpMethod'] == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps('CORS preflight check successful')}

    http_method = event['httpMethod']
    
    # POST (註冊) 不需要驗證 Token
    if http_method == 'POST':
        # ... (POST 邏輯與之前完全相同)
        try:
            body = json.loads(event.get("body", "{}"))
            user_id = body.get("user_id")
            password = body.get("password")

            if not user_id or not password:
                return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "'user_id' and 'password' are required"})}

            sha256 = hashlib.sha256()
            sha256.update(password.encode('utf-8'))
            hashed_password = sha256.hexdigest()

            table.put_item(
                Item={'user_id': user_id, 'password': hashed_password},
                ConditionExpression="attribute_not_exists(user_id)"
            )
            return {"statusCode": 201, "headers": cors_headers, "body": json.dumps({"message": "Account created successfully", "account": user_id})}
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return {"statusCode": 409, "headers": cors_headers, "body": json.dumps({"message": f"Account '{user_id}' already exists"})}
            else:
                traceback.print_exc()
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Error creating account"})}
        except Exception as e:
            traceback.print_exc()
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "An internal error occurred"})}


    # --- 對於需要授權的請求 (GET, PUT)，先驗證 Token ---
    try:
        # 2. 不再從 path 取得 user_id，而是從 Token
        user_id = _get_user_id_from_token(event)
    except TokenError as e:
        return {
            'statusCode': 401, # Unauthorized
            'headers': cors_headers,
            'body': json.dumps({'message': str(e)})
        }

    #==============================================
    #=======      GET 請求 (已驗證 Token)       =======
    #==============================================
    if http_method == 'GET':
        try:
            response = table.get_item(Key={'user_id': user_id})
            
            if 'Item' not in response:
                return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": "User not found"})}
            
            item = response['Item']
            item.pop('password', None)

            return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(item)}
        except ClientError as e:
            print(f"DynamoDB Error on GET: {e.response['Error']['Message']}")
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Error retrieving user data"})}

    #==============================================
    #=======       PUT 請求 (已驗證 Token)       =======
    #==============================================
    elif http_method == 'PUT':
        try:
            # 3. user_id 已從 Token 取得，不需要再從 path 拿
            body = json.loads(event.get("body", "{}"))
            current_password = body.get("current_password")
            new_password = body.get("new_password")

            # --- 分支 1: 變更密碼 ---
            if current_password is not None and new_password is not None:
                # ... (變更密碼的內部邏輯與之前相同)
                response = table.get_item(Key={'user_id': user_id})
                if 'Item' not in response:
                    return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": f"User '{user_id}' not found"})}
                
                stored_password_hash = response['Item'].get('password')
                sha256 = hashlib.sha256()
                sha256.update(current_password.encode('utf-8'))
                hashed_current_password = sha256.hexdigest()

                if hashed_current_password != stored_password_hash:
                    return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Incorrect current password"})}
                
                sha256_new = hashlib.sha256()
                sha256_new.update(new_password.encode('utf-8'))
                hashed_new_password = sha256_new.hexdigest()

                table.update_item(
                    Key={'user_id': user_id},
                    UpdateExpression="SET #pwd = :new_pwd",
                    ExpressionAttributeNames={'#pwd': 'password'},
                    ExpressionAttributeValues={':new_pwd': hashed_new_password}
                )
                return {"statusCode": 200, "headers": cors_headers, "body": json.dumps({"message": "Password updated successfully"})}
            
            # --- 分支 2: 更新使用者資料 ---
            else:
                # ... (更新資料的內部邏輯與之前相同)
                user_name = body.get("user_name")
                user_phone = body.get("user_phone")
                user_address = body.get("user_address")

                if user_name is None and user_phone is None and user_address is None:
                    return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "At least one field to update is required"})}

                update_expression = "SET "
                expression_attribute_values = {}
                
                if user_name is not None: update_expression += "user_name = :name, "; expression_attribute_values[":name"] = user_name
                if user_phone is not None: update_expression += "user_phone = :phone, "; expression_attribute_values[":phone"] = user_phone
                if user_address is not None: update_expression += "user_address = :address, "; expression_attribute_values[":address"] = user_address
                
                update_expression = update_expression.rstrip(', ')
                
                response = table.update_item(
                    Key={'user_id': user_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values,
                    ReturnValues="UPDATED_NEW"
                )
                return {"statusCode": 200, "headers": cors_headers, "body": json.dumps({"message": f"User '{user_id}' updated successfully", "updatedAttributes": response.get('Attributes', {})})}

        except ClientError as e:
            # 這裡不再需要檢查 ConditionalCheckFailedException，因為我們是先驗證 Token
            print(f"DynamoDB Error on PUT: {e.response['Error']['Message']}")
            traceback.print_exc()
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Error updating user data"})}
        except json.JSONDecodeError:
            return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Invalid JSON in request body"})}
        except Exception as e:
            print(f"An unexpected error occurred on PUT: {e}")
            traceback.print_exc()
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Internal server error"})}
    
    else:
        return {'statusCode': 405, 'headers': cors_headers, 'body': json.dumps(f"HTTP method '{http_method}' is not supported")}
