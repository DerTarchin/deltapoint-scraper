from datetime import datetime
import requests
import json
import tdapi
import os

KIBOT_LOGIN = "http://api.kibot.com/?action=login&user=guest&password=guest"
# KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=<STARTDATE>"
KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=08/08/18"
CWD = os.path.dirname(os.path.realpath(__file__))
login = json.load(open(CWD + "/.login"))

def printf(txt):
  print txt,
  LOG = open(CWD + "/log.txt", "a")
  LOG.write(txt)
  LOG.flush()

dateformat = "%m/%d/%Y %H:%M:%S"
def num(n):
  val = float(n.replace(",",""))
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
    if action["amount"] + action["reg_fee"] + action["commission"] != 0:
      parsed.append(action)

  return parsed

def save_data(name, ext, datafolder, data):
  file = datafolder + "/" + name + ext
  f = open(file, "w")
  f.write(json.dumps(data, indent=2))
  return file

def update_td(account, datafolder, year):
  printf( "<< updating " + str(account) + " " + str(year) + " >>\n")

  # log in
  printf( "starting scraper...")
  td = tdapi.TD(login)
  printf( "done\n")

  # switch account to IRA
  printf( "switching to " + account + "...")
  td.account(account)
  printf( "done\n")

  # get transaction history
  printf( "getting transaction history...")
  history = td.history(year)
  parsed = parse_history(history)
  printf( "done\n")

  startdate = None
  symbols = []
  for row in parsed:
    date = datetime.strptime(row["date"], dateformat)
    if not startdate or date < startdate:
      startdate = date
    if "symbol" in row and row["symbol"] not in symbols:
      symbols.append(row["symbol"])

  loggedInKibot = False
  symboldata = []
  printf("getting stock history...\n")
  for s in symbols:
    if symbols[0] is s:
      printf(s.upper())
    else:
      printf(" | " + s.upper())
    if not loggedInKibot:
      requests.get(KIBOT_LOGIN)
    response = requests.get(KIBOT_STOCK.replace("<SYMBOL>",s.upper()).replace("<STARTDATE>",startdate.strftime("%d/%m/%Y"))).text
    sym = {
      "symbol": s,
      "data": {}
    }
    for day in response.split("\r\n"):
      if not day or "," not in day:
        continue
      data = day.split(",")
      sym["data"][data[0]] = {
        "o": float(data[1]),
        "h": float(data[2]),
        "l": float(data[3]),
        "c": float(data[4])
      }
    symboldata.append(sym)
  printf("\ngetting stock history... done\n")

  # quit
  printf( "exiting scraper...")
  td.close()
  printf( "done\n")

  printf( "saving data...")
  files = []
  files.append(save_data("tda_" + account + "_" + str(year), ".json", datafolder, parsed))
  for s in symboldata:
    files.append(save_data(s["symbol"], ".txt", datafolder, s["data"]))

  printf( "done\n")

  # for f in files:
  #   printf(f+"\n")

  return file