from selenium.webdriver.chrome.options import Options
from datetime import date, datetime, timedelta
import unicodedata
import json
import re
import time

try:
    from StringIO import StringIO  # Python 2
except ImportError:
    from io import BytesIO as StringIO  # Python 3

from seleniumrequests import Chrome

try:
    import pandas as pd
except ImportError:
    pd = None


def assert_pd():
    # Common function to check if pd is installed
    if not pd:
        raise ImportError(
            "transactions data requires pandas; "
            "please pip install pandas"
        )


def date(dateraw, format):
    return datetime.strptime(dateraw, format)

def text(el):
    return unicodedata.normalize("NFKD", el.get_property("textContent")).strip()


def get_web_driver(login):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')  # Last I checked this was necessary.
    driver = Chrome(chrome_options=options)

    driver.get("https://www.tdameritrade.com")
    driver.implicitly_wait(20)  # seconds

    driver.find_element_by_id("userid").send_keys(login["u"])
    driver.find_element_by_id("password").send_keys(login["p"])
    driver.find_element_by_class_name("main-header-login-submit").click()

    driver.implicitly_wait(20)  # seconds

    if "login" in driver.current_url:
        qe = driver.find_element_by_css_selector("#login .securityChallenge + .securityP")
        qe = driver.find_element_by_css_selector("#login .securityChallenge + .securityP")
        q = text(qe).replace(text(qe.find_element_by_tag_name("span")), "")

        driver.find_element_by_name("challengeAnswer").send_keys(login["a"][login["q"].index(min(login["q"], key=lambda x:abs(x-(len(q)))))])
        remember = driver.find_element_by_name("rememberDevice")
        if remember.get_property("aria-checked") == "false":
            remember.click()
        driver.find_element_by_css_selector("#login .dijitButtonNode").click()
        driver.implicitly_wait(20)  # seconds

    return driver

def get_transaction_history(driver):
    header_map = {
        "1": "date",
        "3": "description",
        "5": "amount",
        "7": "remaining"
    }

    driver.switch_to.frame(driver.find_element_by_css_selector("iframe#main"))
    driver.implicitly_wait(20)
    links = driver.find_elements_by_css_selector("form td a")
    if links == None or links == False or len(links) == 0:
        driver.switch_to.defaultContent()
        return False
    for link in links:
        if text(link).lower() == "current year":
            link.click()
            time.sleep(1)
            break
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

class MintException(Exception):
    pass

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
        self.driver.find_element_by_id("accountSwitcherSelectBox").click()
        self.driver.implicitly_wait(1)
        options = self.driver.find_elements_by_css_selector("#accountSwitcherSelect_menu .accountNickname")
        for option in options:
            if option.get_property("textContent") == nickname:
                option.click()

        self.driver.implicitly_wait(20)
        time.sleep(3)
        return

    def history(self):
        url = "https://invest.ameritrade.com/grid/p/site#r=jPage/cgi-bin/apps/u/History"
        # url might break often ?
        self.driver.get(url)
        self.driver.implicitly_wait(20)
        history = get_transaction_history(self.driver)
        if history == False or history == None or len(history) == 0:
            # sometimes UI doesn't render
            self.driver.refresh()
            self.driver.implicitly_wait(20)
            time.sleep(2)
            return get_transaction_history(self.driver)
        return history


def main():
    import getpass
    import argparse

    try:
        import keyring
    except ImportError:
        keyring = None

    # Parse command-line arguments {{{
    cmdline = argparse.ArgumentParser()
    cmdline.add_argument(
        "email",
        nargs="?",
        default=None,
        help="The e-mail address for your Mint.com account")
    cmdline.add_argument(
        "password",
        nargs="?",
        default=None,
        help="The password for your Mint.com account")

    cmdline.add_argument(
        "--accounts",
        action="store_true",
        dest="accounts",
        default=False,
        help="Retrieve account information"
        " (default if nothing else is specified)")
    cmdline.add_argument(
        "--budgets",
        action="store_true",
        dest="budgets",
        default=False,
        help="Retrieve budget information")
    cmdline.add_argument(
        "--net-worth",
        action="store_true",
        dest="net_worth",
        default=False,
        help="Retrieve net worth information")
    cmdline.add_argument(
        "--extended-accounts",
        action="store_true",
        dest="accounts_ext",
        default=False,
        help="Retrieve extended account information (slower, "
        "implies --accounts)")
    cmdline.add_argument(
        "--transactions",
        "-t",
        action="store_true",
        default=False,
        help="Retrieve transactions")
    cmdline.add_argument(
        "--extended-transactions",
        action="store_true",
        default=False,
        help="Retrieve transactions with extra information and arguments")
    cmdline.add_argument(
        "--start-date",
        nargs="?",
        default=None,
        help="Earliest date for transactions to be retrieved from. "
        "Used with --extended-transactions. Format: mm/dd/yy")
    cmdline.add_argument(
        "--include-investment",
        action="store_true",
        default=False,
        help="Used with --extended-transactions")
    cmdline.add_argument(
        "--skip-duplicates",
        action="store_true",
        default=False,
        help="Used with --extended-transactions")
    # Displayed to the user as a postive switch, but processed back
    # here as a negative
    cmdline.add_argument(
        "--show-pending",
        action="store_false",
        default=True,
        help="Exclude pending transactions from being retrieved. "
        "Used with --extended-transactions")
    cmdline.add_argument(
        "--filename", "-f",
        help="write results to file. can "
        "be {csv,json} format. default is to write to "
        "stdout.")
    cmdline.add_argument(
        "--keyring",
        action="store_true",
        help="Use OS keyring for storing password "
        "information")

    options = cmdline.parse_args()

    if options.keyring and not keyring:
        cmdline.error("--keyring can only be used if the `keyring` "
                      "library is installed.")

    try:  # python 2.x
        from __builtin__ import raw_input as input
    except ImportError:  # python 3
        from builtins import input
    except NameError:
        pass

if __name__ == "__main__":
    main()
