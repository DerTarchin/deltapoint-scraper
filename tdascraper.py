from datetime import datetime
from iexfinance.stocks import Stock
from bs4 import BeautifulSoup
import requests
import json
import tdapi
import os

KIBOT_LOGIN = "http://api.kibot.com/?action=login&user=guest&password=guest"
# KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=<STARTDATE>"
KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=08/08/18&splitadjusted=1"
Y_FINANCE_STOCK = "https://finance.yahoo.com/quote/<SYMBOL>/"
CWD = os.path.dirname(os.path.realpath(__file__))
login = json.load(open(CWD + "/.login"))
loggedInKibot = False
dateformat = "%m/%d/%Y %H:%M:%S"

RUN_IEX = True
RUN_RH = True


def printf(txt):
    print txt,
    LOG = open(CWD + "/log.txt", "a")
    LOG.write(txt)
    LOG.flush()


def num(n):
    val = float(n.replace(",", ""))
    return int(val) if int(val) == val else val


def parse_history(hist):
    def parse_desc(desc):
        ldesc = desc.lower()
        if any(x in ldesc for x in ["bought", "sold"]):
            sep = ldesc.split(" ")
            return {
                "type": "buy" if "bought" in sep[0] else "sell",
                "shares": num(sep[1]),
                "symbol": str(sep[2]),
                "price": num(sep[4])
            }
        elif "fee" in ldesc:
            return {"type": "fee"}
        elif "funding" in ldesc:
            return {"type": "transfer"}
        elif "dividend" in ldesc:
            div_sym = None
            if "~" in ldesc:
                div_sym = ldesc.split('~')[-1]
            else:
                div_sym = ldesc.replace(')', '(').split('(')[-2]
            return {
                "type": "dividend",
                "symbol": div_sym
            }
        else:
            return {"type": "adj"}
    parsed = []
    for row in hist:
        action = {
            "text": row["description"],
            "date": row["date"].strftime("%m/%d/%Y %H:%M:%S"),
            "amount": num(row["amount"]),
            # "remaining": num(row["net_cash_balance"]),
            "reg_fee": num(row["reg_fee"]),
            "commission": num(row["commission"]),
        }
        desc = parse_desc(row["description"])
        for key in desc.keys():
            action[key] = desc[key]
        if action["amount"] + action["reg_fee"] + action["commission"] != 0 and "cash alternatives" not in action["text"].lower():
            parsed.append(action)

    return parsed


def save_data(name, ext, datafolder, data):
    file = datafolder + "/" + name + ext
    f = open(file, "w")
    f.write(json.dumps(data, indent=2))
    return file


def getKibotData(endpoint):
    if not loggedInKibot:
        requests.get(KIBOT_LOGIN)
    attempts = 0
    response = None
    while attempts < 5:
        req_response = requests.get(endpoint)
        response = req_response.text
        # sometimes kibot returns an error (499 Not Allowed)
        # in those cases, while loop will attempt again
        if "kibot" not in response:
            return response.split("\r\n")
    return response


def update_td(account, datafolder, year):
    printf("<< updating " + str(account) + " " + str(year) + " >>\n")

    # log in
    printf("starting scraper...")
    td = tdapi.TD(login)
    printf("done\n")

    # switch account to IRA
    printf("switching to " + account + "...")
    td.account(account)
    printf("done\n")

    # get transaction history
    printf("getting transaction history...")
    history = td.history(year)
    parsed = parse_history(history)
    printf("done\n")

    # get all active positions (in case no transaction history for the year)
    printf("getting active positions...")
    active_positions = td.positions()
    printf("done\n")

    startdate = None
    symbols = []
    for row in parsed:
        date = datetime.strptime(row["date"], dateformat)
        if not startdate or date < startdate:
            startdate = date
        if "symbol" in row and row["symbol"] not in symbols:
            symbols.append(row["symbol"])

    for s in active_positions:
        if s not in symbols:
            symbols.append(s)

    symboldata = []
    printf("getting stock history...\n")
    for s in symbols:
        if s is not symbols[0]:
            printf("\n")
        printf("| " + str(s).upper())

        endpoint = KIBOT_STOCK.replace("<SYMBOL>", s.upper()).replace("<STARTDATE>", startdate.strftime("%d/%m/%Y"))
        kibotData = getKibotData(endpoint)
        sym = {
            "symbol": s,
            "data": {}
        }
        latest_kibot_day = None

        for day in kibotData:
            if not day or "," not in day:
                continue
            data = day.split(",")
            latest_kibot_day = data[0]
            sym["data"][data[0]] = {
                "o": float(data[1]),
                "h": float(data[2]),
                "l": float(data[3]),
                "c": float(data[4])
            }

        # get updated close data from IEX Cloud
        if RUN_IEX:
            api_data = Stock(str(s.upper()), token=str(login["iex"])).get_quote()
            api_latest_date = datetime.fromtimestamp(api_data["lastTradeTime"] / 1000).strftime("%m/%d/%Y")
            if api_latest_date != latest_kibot_day:
                # latest_kibot_day = api_latest_date
                sym["data"][api_latest_date] = {
                    "o": api_data["latestPrice"],  # free tier doesn't include open
                    "h": api_data["latestPrice"],  # free tier doesn't include high
                    "l": api_data["latestPrice"],  # free tier doesn't include low
                    "c": api_data["latestPrice"]
                }
                # get true open, high, low values of the day from Yahoo Finance
                page = requests.get(Y_FINANCE_STOCK.replace("<SYMBOL>", s.upper()))
                soup = BeautifulSoup(page.content, 'html.parser')
                sym["data"][api_latest_date]["o"] = float(soup.find('td', attrs={'data-test': 'OPEN-value'}).text)
                lh = soup.find('td', attrs={'data-test': 'DAYS_RANGE-value'}).text.split(" - ")
                sym["data"][api_latest_date]["l"] = float(lh[0])
                sym["data"][api_latest_date]["h"] = float(lh[1])

        status_str = ""
        spaces = "     " if len(s) == 3 else "    "
        if not latest_kibot_day:
            status_str += spaces + "none"
        else:
            status_str += spaces + latest_kibot_day + "  " + str(sym["data"][latest_kibot_day]["c"])
        if api_latest_date != latest_kibot_day:
            tabs = "\t\t" if len(status_str) < 23 else "\t"
            status_str += tabs + "|  IEX:  " + api_latest_date + "  " + str(sym["data"][api_latest_date]["c"])
        printf(status_str)
        symboldata.append(sym)
    printf("\ngetting stock history... done\n")

    # quit
    printf("exiting scraper...")
    td.close()
    printf("done\n")

    printf("saving data...")
    files = []
    files.append(save_data("tda_" + account + "_" + str(year), ".json", datafolder, parsed))
    for s in symboldata:
        files.append(save_data(s["symbol"], ".txt", datafolder, s["data"]))

    printf("done\n")

    # for f in files:
    #   printf(f+"\n")

    return file
