import json
import os
import datetime
import boto3
import jwt
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# 從環境變數讀取設定
TABLETS_TABLE_NAME = "plaques" # os.environ.get("TABLETS_TABLE_NAME", "plaques")
# 確保您在部署時或在 template.yaml 的 Environment Variables 中設定了 JWT_SECRET_KEY
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")


def lambda_handler(event, context):
    """
    主 Lambda 處理函數，根據 HTTP 方法路由到不同的 CRUD 操作。
    支援的端點:
    - POST /plaques: 新增一個 Plaque
    - GET /plaques: 取得使用者所有的 Plaque 列表
    - GET /plaques/{id}: 根據 timestamp (id) 取得單一 Plaque
    - PUT /plaques/{id}: 更新一個已存在的 Plaque
    - DELETE /plaques/{id}: 刪除一個 Plaque
    """

    # ---- DynamoDB 連線邏輯 ----
    if os.environ.get("AWS_SAM_LOCAL"):
        # 本地測試時，連接到本地的 DynamoDB 容器
        dynamodb_endpoint = "http://192.168.200.144:8000" # <-- 請換成你自己的 IP
        dynamodb_resource = boto3.resource("dynamodb", endpoint_url=dynamodb_endpoint)
    else:
        # 在 AWS 環境中，Boto3 會自動找到對應區域的 DynamoDB
        dynamodb_resource = boto3.resource("dynamodb")

    table = dynamodb_resource.Table(TABLETS_TABLE_NAME)

    # ---- CORS 標頭設定 ----
    # 確保允許所有需要的 HTTP 方法
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
    }

    # 1. (安全性) 驗證 JWT Token
    try:
        auth_header = event['headers'].get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Missing or invalid token"})}
        
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # 從 token 中取得已驗證的使用者帳號，確保使用者只能操作自己的資料
        user_id = payload['sub']

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Token is invalid or has expired"})}
    except Exception:
        return {"statusCode": 401, "headers": cors_headers, "body": json.dumps({"message": "Unauthorized"})}


    http_method = event.get('httpMethod')
    
    # ===================================================================
    # --- 處理 POST 請求 (新增 Plaque) ---
    # ===================================================================
    if http_method == 'POST':
        try:
            body = json.loads(event.get("body", "{}"))
            plaque_data = body.get("plaque_data")
            plaque_name = body.get("plaque_name")
            plaque_type = body.get("plaque_type")
            user_name = body.get("user_name")
            user_phone = body.get("user_phone")
            user_address = body.get("user_address")

            plaque_subtype = body.get("plaque_subtype")
            misfortune_dispelling_data = body.get("misfortune_dispelling_data")

            if not plaque_data or not plaque_name:
                return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "'plaque_data' and 'plaque_name' are required"})}

        except (json.JSONDecodeError, TypeError):
            return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Invalid or missing request body"})}

        try:
            timestamp = datetime.datetime.utcnow().isoformat() + "Z"
            item_to_add = {
                'user_id': user_id,
                'timestamp': timestamp,
                'plaque_name': plaque_name,
                'plaque_type': plaque_type,
                "user_name": user_name,
                "user_phone": user_phone,
                "user_address": user_address,
                'plaque_data': plaque_data
            }

            if misfortune_dispelling_data:
                item_to_add['misfortune_dispelling_data'] = misfortune_dispelling_data
            if plaque_subtype:
                item_to_add['plaque_subtype'] = plaque_subtype

            table.put_item(Item=item_to_add)
            print(f"Successfully added plaque for user_id: {user_id}")
            
            return {
                "statusCode": 201, # Created
                "headers": cors_headers,
                "body": json.dumps({"message": "Plaque added successfully", "item": item_to_add})
            }
        except ClientError as e:
            print(f"DynamoDB POST Error: {e.response['Error']['Message']}")
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to add plaque"})}
            
    # ===================================================================
    # --- 處理 GET 請求 (查詢列表或單一項目) ---
    # ===================================================================
    elif http_method == 'GET':
        path_params = event.get('pathParameters')
        
        # 情況 1: 請求單一 Plaque (e.g., GET /plaques/{id})
        if path_params and 'id' in path_params:
            plaque_id = path_params['id']
            print(f"Fetching single plaque with id: {plaque_id} for user: {user_id}")
            
            try:
                response = table.get_item(Key={'user_id': user_id, 'timestamp': plaque_id})
                item = response.get('Item')
                if item:
                    return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(item)}
                else:
                    return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": "Plaque not found"})}
            except ClientError as e:
                print(f"DynamoDB GET item Error: {e.response['Error']['Message']}")
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to retrieve plaque"})}

        # 情況 2: 請求所有 Plaque (e.g., GET /plaques)
        else:
            print(f"Fetching all plaques for user: {user_id}")
            try:
                response = table.query(
                    KeyConditionExpression=Key('user_id').eq(user_id),
                    ProjectionExpression="user_id, plaque_name, plaque_type, #ts",
                    ExpressionAttributeNames={"#ts": "timestamp"}
                )
                items = response.get('Items', [])
                return {"statusCode": 200, "headers": cors_headers, "body": json.dumps({"message": "Plaques retrieved successfully", "plaques": items})}
            except ClientError as e:
                print(f"DynamoDB GET list Error: {e.response['Error']['Message']}")
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to retrieve plaques"})}

    # ===================================================================
    # --- 處理 PUT 請求 (更新 Plaque) ---
    # ===================================================================
    elif http_method == 'PUT':
        path_params = event.get('pathParameters')
        
        if not path_params or 'id' not in path_params:
            return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Missing plaque ID in path"})}
        
        plaque_id = path_params['id']

        try:
            body = json.loads(event.get("body", "{}"))
            update_fields = {
                'plaque_name': body.get("plaque_name"),
                'plaque_type': body.get("plaque_type"),
                'user_name': body.get("user_name"),
                'user_phone': body.get("user_phone"),
                'user_address': body.get("user_address"),
                'plaque_data': body.get("plaque_data")
            }

            aa = body.get("plaque_subtype")
            bb = body.get("misfortune_dispelling_data")

            #plaque_subtype = body.get("plaque_subtype")
            #misfortune_dispelling_data = body.get("misfortune_dispelling_data")
            
            if aa:
                update_fields['plaque_subtype'] = aa
            if bb:
                update_fields['misfortune_dispelling_data'] = bb

            # 過濾掉值為 None 的欄位，只更新有提供的欄位
            update_fields = {k: v for k, v in update_fields.items() if v is not None}

            if not update_fields:
                 return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Request body must contain at least one field to update"})}

        except (json.JSONDecodeError, TypeError):
            return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Invalid request body"})}

        try:
            update_expression_parts = [f"#{key} = :{key}" for key in update_fields.keys()]
            update_expression = "SET " + ", ".join(update_expression_parts)
            
            expression_attribute_values = {f":{key}": value for key, value in update_fields.items()}
            expression_attribute_names = {f"#{key}": key for key in update_fields.keys()}

            response = table.update_item(
                Key={'user_id': user_id, 'timestamp': plaque_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ExpressionAttributeNames=expression_attribute_names,
                ConditionExpression="attribute_exists(user_id)",
                ReturnValues="UPDATED_NEW"
            )

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({"message": "Plaque updated successfully", "updatedAttributes": response.get('Attributes', {})})
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": "Plaque not found"})}
            else:
                print(f"DynamoDB UPDATE Error: {e.response['Error']['Message']}")
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to update plaque"})}

    # ===================================================================
    # --- 處理 DELETE 請求 (刪除 Plaque) ---
    # ===================================================================
    elif http_method == 'DELETE':
        path_params = event.get('pathParameters')
        
        if not path_params or 'id' not in path_params:
            return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"message": "Missing plaque ID in the path"})}
        
        plaque_id = path_params['id']
        print(f"Attempting to delete plaque with id: {plaque_id} for user: {user_id}")

        try:
            table.delete_item(
                Key={'user_id': user_id, 'timestamp': plaque_id},
                ConditionExpression="attribute_exists(user_id)"
            )
            print(f"Successfully deleted plaque {plaque_id}")
            return {"statusCode": 204, "headers": cors_headers, "body": ""}
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                print(f"Plaque not found for deletion: {plaque_id}")
                return {"statusCode": 404, "headers": cors_headers, "body": json.dumps({"message": "Plaque not found"})}
            else:
                print(f"DynamoDB DELETE Error: {e.response['Error']['Message']}")
                return {"statusCode": 500, "headers": cors_headers, "body": json.dumps({"message": "Failed to delete plaque"})}

    # ===================================================================
    # --- 處理其他不支持的方法 ---
    # ===================================================================
    else:
        return {"statusCode": 405, "headers": cors_headers, "body": json.dumps({"message": "Method not allowed"})}
