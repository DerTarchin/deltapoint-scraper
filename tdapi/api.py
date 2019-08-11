import selenium
from selenium import webdriver
# from selenium.webdriver.chrome.options import Options
from selenium.webdriver.firefox.options import Options
from datetime import date, datetime, timedelta
import unicodedata
import json
import re
import time
import os

def date(dateraw, format):
    return datetime.strptime(dateraw, format)

def text(el):
    return unicodedata.normalize("NFKD", el.get_property("textContent")).strip()


def get_web_driver(login):
    options = Options()

    options.add_argument("--window-size=1920,1080")
    # options.add_argument("--disable-extensions")
    # options.add_argument("--proxy-server='direct://'")
    # options.add_argument("--proxy-bypass-list=*")
    # options.add_argument("--start-maximized")
    options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    # options.add_argument('--disable-dev-shm-usage')
    # options.add_argument('--no-sandbox')
    # options.add_argument('--ignore-certificate-errors')

    # driver = Chrome(chrome_options=options)
    # driver = webdriver.Chrome(browser = webdriver.Chrome(executable_path=r"C:\path\to\chromedriver.exe")
    
    script_dir = os.path.dirname(__file__) #<-- absolute dir the script is in
    # driver = webdriver.Chrome(executable_path=os.path.join(script_dir, "chromedriver"), chrome_options=options)

    driver = webdriver.Firefox(executable_path=os.path.join(script_dir, "geckodriver"), firefox_options=options)

    driver.get("https://www.tdameritrade.com")
    driver.implicitly_wait(200)  # seconds

    driver.find_element_by_id("userid").send_keys(login["u"])
    driver.find_element_by_id("password").send_keys(login["p"])
    driver.find_element_by_class_name("main-header-login-submit").click()

    driver.implicitly_wait(200)  # seconds

    if "login" in driver.current_url:
        qe = driver.find_element_by_css_selector("#login .securityChallenge + .securityP")
        qe = driver.find_element_by_css_selector("#login .securityChallenge + .securityP")
        q = text(qe).replace(text(qe.find_element_by_tag_name("span")), "")

        driver.find_element_by_name("challengeAnswer").send_keys(login["a"][login["q"].index(min(login["q"], key=lambda x:abs(x-(len(q)))))])
        remember = driver.find_element_by_name("rememberDevice")
        if remember.get_property("aria-checked") == "false":
            remember.click()
        driver.find_element_by_css_selector("#login .dijitButtonNode").click()
        driver.implicitly_wait(200)  # seconds
    return driver

def get_transaction_history(driver, year):
    header_map = {
        "1": "date",
        "3": "description",
        "5": "amount",
        "7": "commission",
        "9": "reg_fee",
        "11": "net_cash_balance"
    }

    driver.switch_to.frame(driver.find_element_by_css_selector("iframe#main"))
    driver.implicitly_wait(200)
    yearlinks = driver.find_element_by_id("viewYearContainer")
    links = yearlinks.find_elements_by_css_selector("a")
    if links == None or links == False or len(links) == 0:
        driver.switch_to.defaultContent()
        return False
    
    for link in links:
        # website updated 
        # if text(link).lower() == "current year":
        #     currLink = link
        # if text(link).lower() == "previous year":
        #     prevLink = link
        if text(link) == str(datetime.now().year):
            currLink = link
        if text(link) == str(datetime.now().year - 1):
            prevLink = link

    link = prevLink if year else currLink
    link.click()
    time.sleep(1)

    if year:
        yearSelections = [driver.find_element_by_name("FROM_YEAR"), driver.find_element_by_name("TO_YEAR")]
        for select in yearSelections:
            options = select.find_elements_by_tag_name("option")
            for opt in options:
                if opt.get_attribute("value") == str(year):
                    opt.click()
                    time.sleep(1)
        viewlink = driver.find_element_by_id("viewbtn")
        if viewlink:
            viewlink.click()
            time.sleep(1)
            driver.implicitly_wait(200)

    rows = driver.find_elements_by_css_selector("form #paging1 + table tr[class*='row']")
    data = []
    for row in rows:
        cells = row.find_elements_by_tag_name("td")
        rowData = {}
        for key in header_map.keys():
            if header_map[key] == "date":
                rowData[header_map[key]] = date(text(cells[int(key)]), "%m/%d/%Y  %H:%M:%S")
            else:
                rowData[header_map[key]] = text(cells[int(key)])
        data.append(rowData)
    return data


IGNORE_FLOAT_REGEX = re.compile(r"[$,%]")
def parse_float(str_number):
    try:
        return float(IGNORE_FLOAT_REGEX.sub(str_number, ""))
    except ValueError:
        return None

class TD(object):
    driver = None

    def __init__(self, login=None):
        if login:
            self.login(login)

    @classmethod
    def create(cls, login):
        return TD(login)

    def close(self):
        """Logs out and quits the current web driver/selenium session."""
        if not self.driver:
            return

        try:
            self.driver.implicitly_wait(1)
            self.driver.find_element_by_css_selector(".logout a").click()
        except:
            pass

        self.driver.quit()
        self.driver = None

    def login(self, login):
        if self.driver:
            return
        self.driver = get_web_driver(login)

    def account(self, nickname):
        time.sleep(1)
        # print self.driver.page_source.encode("utf-8")
        sbox = self.driver.find_element_by_id("accountSwitcherSelectBox")
        sbox.click()
        self.driver.implicitly_wait(200)
        options = self.driver.find_elements_by_css_selector("#accountSwitcherSelect_menu .accountNickname")
        for option in options:
            if option.get_property("textContent") == nickname:
                option.click()

        self.driver.implicitly_wait(200)
        time.sleep(3)
        return

    def history(self, year=None):
        url = "https://invest.ameritrade.com/grid/p/site#r=jPage/cgi-bin/apps/u/History"
        # url might break often ?
        self.driver.get(url)
        self.driver.implicitly_wait(200)

        if year == datetime.now().year:
            year = None

        history = get_transaction_history(self.driver, year)
        if history == False or history == None or len(history) == 0:
            # sometimes UI doesn't render
            self.driver.refresh()
            self.driver.implicitly_wait(200)
            time.sleep(2)
            return get_transaction_history(self.driver, year)
        return history