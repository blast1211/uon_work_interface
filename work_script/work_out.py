from selenium import webdriver
from selenium.webdriver.common.by import By
import time


cnt = 0
while True:
	try:
		browser = webdriver.Chrome()

		#browser = webdriver.Chrome() # 현재파일과 동일한 경로일 경우 생략 가능

		# 1. 네이버 이동
		#browser.get('https://cubox.daouoffice.com/login')
		browser.get('https://gw.cubox.ai/#/login')
		time.sleep(3.5)
		# 2. 로그인 버튼 클릭
		browser.find_element('id','reqLoginId').send_keys('chansol.oh')
		time.sleep(0.1)
		browser.find_element('xpath','//*[@id="wrap"]/div[1]/div[2]/div/div[2]/div[4]/div[1]/div/button').click()
		time.sleep(0.1)
		browser.find_element('id','reqLoginPw').send_keys('1!dhcksthf')
		time.sleep(0.1)
		browser.find_element('xpath','//*[@id="wrap"]/div[1]/div[2]/div/div[2]/div[4]/div[1]/div/button').click()
		time.sleep(3.0)
		browser.find_element('xpath','//*[@id="container"]/ul/li[2]').click()
		time.sleep(2.0)
		browser.find_element('xpath','/html/body/div[3]/div[4]/div[2]/div/div[3]/div[2]/button').click()
		time.sleep(1.0)
		browser.quit()
		break
	except:
		browser.find_element('xpath','//*[@id="container"]/ul/li[2]').click()
		browser.quit()
		time.sleep(1)
		cnt+=1
		if cnt>5:
			browser.quit()
			break
		
# 4. 로그인 버튼 클릭
#browser.find_element('id','login_submit').click()
#time.sleep(1.5)
#browser.find_element('xpath','//*[@id="advancedGuideLayer"]/div/div[5]/a[1]').click()
#time.sleep(1)
#browser.find_element('xpath','//*[@id="workIn"]').click()
#browser.find_element_by_xpath('//*[@id="workOut"]').click()
#browser.quit()

