from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import pandas as pd

options = webdriver.ChromeOptions()
options.add_argument('--start-maximized')
service = Service('H:\\DataAnalytics_project\\real_estate_analysis\\chromedriver-win64\\chromedriver.exe')
driver = webdriver.Chrome(service=service, options=options)
driver.get('https://www.google.com')

# Accept cookies if the button appears (for EU/UK users)
try:
    accept = driver.find_element(By.XPATH, "//button[contains(., 'Accept')]")
    accept.click()
except Exception:
    pass

# Scrape all links on the page
links = driver.find_elements(By.TAG_NAME, "a")
data = []
for link in links:
    text = link.text.strip()
    href = link.get_attribute("href")
    if text and href:
        data.append({"text": text, "url": href})

# Save to CSV
df = pd.DataFrame(data)
df.to_csv("google_links.csv", index=False)
print("Saved google_links.csv with", len(df), "links.")

driver.quit()