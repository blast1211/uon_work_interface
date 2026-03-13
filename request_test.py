import requests

url = "https://gw.cubox.ai/human/common/judgeTimeManagement/getJudgeTimeManagement"

headers = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

data = {
    "type": "WEB",
    "judgeData": {
        "empCd": "10017",
        "deptCd": "20211",
        "coCd": "2000",
        "attendFg": "4"
    }
}

response = requests.post(url, headers=headers, json=data)

print("Status Code:", response.status_code)
print("Response:", response.text)
