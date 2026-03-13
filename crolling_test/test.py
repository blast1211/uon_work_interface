import requests
import time
import random

session = requests.Session()

# 현재 시간 기반으로 timestamp 생성 (마지막 3자리는 랜덤)
timestamp = int(time.time() * 1000)
timestamp = (timestamp // 1000) * 1000 + random.randint(0, 999)
print("time stamp : ",timestamp)
# 토큰 요청
token_url = f"https://gw.cubox.ai/get_token/?url=/gw/gw050B01&_={timestamp}"
response = session.get(token_url)
print(response.json())