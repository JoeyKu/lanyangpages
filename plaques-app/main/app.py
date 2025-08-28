# src/app.py
import os

def lambda_handler(event, context):
    
    try:
        # 獲取當前檔案的路徑
        dir_path = os.path.dirname(os.path.realpath(__file__))
        html_file_path = os.path.join(dir_path, 'index.html')

        # 讀取 HTML 檔案內容
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html; charset=utf-8"
            },
            "body": html_content
        }
    except FileNotFoundError:
        return {
            "statusCode": 404,
            "headers": { "Content-Type": "text/plain" },
            "body": "Error: index.html not found."
        }
