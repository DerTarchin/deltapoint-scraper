from datetime import datetime
import requests
import json
import tdapi
import os

KIBOT_LOGIN = "http://api.kibot.com/?action=login&user=guest&password=guest"
KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=<STARTDATE>"
CWD = os.path.dirname(os.path.realpath(__file__))
login = json.load(open(CWD + "/.login"))

def printf(txt):
  print txt,
  LOG = open(CWD + "/log.txt", "a")
  LOG.write(txt)
  LOG.flush()

dateformat = "%m/%d/%Y %H:%M:%S"
def num(n):
  return float(n.replace(",",""))

def parse_history(hist):
  
  def parse_desc(desc):
    ldesc = desc.lower()
    if any(x in ldesc for x in ["bought", "sold"]):
      sep = ldesc.split(" ")
      return {
        "type": "buy" if "bought" in sep[0] else "sell",
        "shares": num(sep[1]),
        "symbol": sep[2],
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
      "date": row["date"].strftime("%m/%d/%Y %H:%M:%S"),
      "amount": num(row["amount"]),
      "remaining": num(row["remaining"]),
    }
    desc = parse_desc(row["description"])
    for key in desc.keys():
      action[key] = desc[key]
    parsed.append(action)

  return parsed

def save_data(name, ext, datafolder, data):
  file = datafolder + "/" + name + ext
  f = open(file, "w")
  f.write(json.dumps(data, indent=2))
  return file

def update_td(account, datafolder):
  printf( "<< updating " + str(account) + " " + str(datetime.now().year) + " >>\n")

  # log in
  printf( "starting scraper...")
  td = tdapi.TD(login)
  printf( "done\n")

  # switch account to IRA
  printf( "switching to " + account + "...")
  td.account(account)
  printf( "done\n")

  # get transaction history
  printf( "getting history...")
  history = td.history()
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
  for s in symbols:
    printf( "getting $" + s.upper() + " data...")
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
    printf( "done\n" if len(s) < 4 else "done\n")

  # quit
  printf( "exiting scraper...")
  td.close()
  printf( "done\n")

  printf( "saving data...")
  files = []
  files.append(save_data("tda_" + account + "_" + str(datetime.now().year), ".json", datafolder, parsed))
  for s in symboldata:
    files.append(save_data(s["symbol"], ".txt", datafolder, s["data"]))

  printf( "done\n")

  for f in files:
    printf(f+"\n")
  return file