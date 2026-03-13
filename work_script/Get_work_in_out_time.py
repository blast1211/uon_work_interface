from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import datetime
import json


ID = "oh.chansol"
PW = "1!dhcksthf"

time_check_data_url = "https://gw.cubox.ai/human/hrd0410/selectTab2"  # ← 여기다가 개발자 도구에서 찾은 Request URL을 넣어줌
time_check_url = "https://gw.cubox.ai/#/HP/HPD0220/HPD0220"

today_info_data_url = "https://gw.cubox.ai/human/common/judgeTimeManagement/getTodayComeLeaveInfo"
today_info_url = "https://gw.cubox.ai/#/"


#driver.find_element('xpath','/html/body/div[2]/div[5]/div[2]/div/div[3]/div[2]/button').click()
#time.sleep(1.0)

# driver.find_element('xpath','//*[@id="tangoMenu"]/div/ul/li[6]').click()
# time.sleep(1.0)

# time_check_data_url = "https://gw.cubox.ai/human/hrd0410/selectTab2"  # ← 여기다가 개발자 도구에서 찾은 Request URL을 넣어줌
# # driver.execute_cdp_cmd("Network.enable", {})
# # driver.get("https://gw.cubox.ai/#/HP/HPD0220/HPD0220")

# time_check_url = "https://gw.cubox.ai/#/HP/HPD0220/HPD0220"
# while True:
# 	driver.get(time_check_url)
# 	time.sleep(0.5)
# 	if driver.current_url == time_check_url:
# 		break

# time.sleep(4)

class OverTime:
	def __init__(self):
		self.today = datetime.datetime.today()
		self.weekday = self.today.weekday()

		chrome_options = Options()
		# chrome_options.add_argument('--headless')  # 창 안 띄우고 실행
		# chrome_options.add_argument('--disable-gpu')  # GPU 비활성화 (일부 환경에서 필요)
		# chrome_options.add_argument('--no-sandbox')  # 리눅스에서 권한 문제 방지
		# chrome_options.add_argument('--disable-dev-shm-usage')  # 메모리 문제 방지
		chrome_options.add_argument("--enable-logging")
		chrome_options.add_argument("--v=1")
		chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # 성능 로그 활성화

		self.driver = webdriver.Chrome(options=chrome_options)

	def run_chrome_driver(self):
		self.driver.get('https://gw.cubox.ai/#/login')
		stage = 0
		try_cnt = 0
		while True:
			try:
				if stage ==0:
					element = self.driver.find_element('id','reqLoginId')
					element.send_keys(ID)
					self.driver.find_element('xpath','//*[@id="wrap"]/div[1]/div[2]/div/div[2]/div[4]/div[1]/div/button').click()
					stage+=1
					try_cnt = 0
				elif stage == 1:
					self.driver.find_element('id','reqLoginPw').send_keys(PW)
					self.driver.find_element('xpath','//*[@id="wrap"]/div[1]/div[2]/div/div[2]/div[4]/div[1]/div/button').click()
					stage+=1
					try_cnt = 0
					break

			except:
				print("err")
				try_cnt +=1
				if try_cnt>10000:
					break


	def get_data(self, data_url, page_url=""):
		if page_url != "":
			while True:
				try:
					time.sleep(0.5)
					self.driver.get(page_url)
					if self.driver.current_url == page_url:
						break
				except :
					print("err")
					try_cnt +=1
					if try_cnt>10000:
						break
		time.sleep(5)
		logs = self.driver.get_log("performance")
		request_data = {}

		for log in logs:
			try:
				log_data = json.loads(log["message"])["message"]

				# 1️⃣ Network.requestWillBeSent 이벤트에서 요청 데이터 확인
				if log_data["method"] == "Network.requestWillBeSent":
					request_info = log_data["params"]["request"]

					# 요청 방식이 POST이고, 특정 URL에 대한 요청인지 확인
					if request_info["method"] == "POST" and data_url in request_info["url"]:

						request_id = log_data["params"]["requestId"]  # 요청 ID 저장
						request_data[request_id] = {
							"url": request_info["url"],
							"postData": request_info.get("postData", "없음"),
						}
						print(f"✅ [POST 요청 감지] {request_info['url']}")
						print(f"📄 POST 데이터: {request_info.get('postData', '없음')}")
						time.sleep(0.1)
				# 2️⃣ Network.responseReceived 이벤트에서 응답 데이터 확인
				if log_data["method"] == "Network.responseReceived":
					request_id = log_data["params"]["requestId"]  # 요청 ID 가져오기

					# 요청과 응답 매칭 (requestId가 같아야 함)
					if request_id in request_data:
						response_url = request_data[request_id]["url"]
						# print(f"🔄 [응답 수신] {response_url}")

						# 3️⃣ Network.getResponseBody를 사용하여 실제 응답 데이터 가져오기
						response_body = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
						# print(f"📩 Response 데이터: {response_body['body']}")  # 실제 응답 본문 출력
						self.data = json.loads(response_body["body"])["resultData"]
						time.sleep(0.1)
						return self.data
			except (json.JSONDecodeError, KeyError):
				pass  # JSON 오류 무시
	def cal_over_time(self,comeTm, leaveTm):
		t1 = datetime.timedelta(hours=int(comeTm[:2]) , minutes=int(comeTm[2:]))
		t2 = datetime.timedelta(hours=int(leaveTm[:2]), minutes=int(leaveTm[2:]))
		return (t2-t1).total_seconds() / 60
	
	def cal_off_time(self,date_name, comeTm, leaveTm):
		if date_name == "휴일": return 0
		elif date_name == "오전반차" :
			return -4*60 + self.cal_over_time(comeTm, leaveTm)
		elif date_name == "오후반차" :
			return -4*60 + self.cal_over_time(comeTm, leaveTm)
		elif date_name == "시간연차" : return 0
		else:
			return -9*60 + self.cal_over_time(comeTm, leaveTm)

	def cal_ot_on_date(self, yy,mm,dd):
		target_date = datetime.date(yy, mm, dd)
		target_week_num = target_date.weekday()
		target_day_list = [f"{yy}{mm:02d}{dd-i-1:02d}" for i in range(target_week_num) if dd-i-1 >0]
		total_ot = 0
		for t_day in target_day_list:
			for data in self.data:
				if data["atDt"] == t_day:
					comeTm = data["comeTm"] if data["comeTm"]!="" else "0900"
					leaveTm = data["leaveTm"] if data["leaveTm"] !="" else "1800"
					total_ot += self.cal_off_time(data["attresultNm"], comeTm, leaveTm)

		return total_ot
	
	def cal_today_ot(self):
		today_data = self.get_data(today_info_data_url, today_info_url)
		if today_data["comeTm"] != "" or today_data["leaveTm"] != "":
			today_ot = self.cal_off_time("", today_data["comeTm"][-4:], today_data["leaveTm"][-4:])
		else: today_ot = 0
		self.get_data(time_check_data_url,time_check_url)

		return self.cal_ot_on_date(self.today.year, self.today.month, self.today.day) + today_ot

ot = OverTime()
ot.run_chrome_driver()

import requests

url = "https://gw.cubox.ai/human/common/judgeTimeManagement/getJudgeTimeManagement"

headers = {
    "Authorization": "Bearer gcmsAmaranth35135|2249|uDEThTzcBheYz4oQ475hMspoblr1QG",
    "Cookie": (
        "oAuthToken=gcmsAmaranth35135%7C2249%7CuDEThTzcBheYz4oQ475hMspoblr1QG; "
        "BIZCUBE_AT=gcmsAmaranth35135%7C2249%7CuDEThTzcBheYz4oQ475hMspoblr1QG; "
        "BIZCUBE_HK=80353167303381239268196001426943087866910204"
    ),
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
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
time.sleep(3)
response = requests.post(url, headers=headers, json=data)

print("Status Code:", response.status_code)
print("Response:", response.text)



print(ot.cal_today_ot())












# driver.quit()
		

