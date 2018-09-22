from datetime import datetime
import requests
import json
import tdapi
import os

KIBOT_LOGIN = "http://api.kibot.com/?action=login&user=guest&password=guest"
KIBOT_STOCK = "http://api.kibot.com/?action=history&symbol=<SYMBOL>&interval=daily&startdate=<STARTDATE>"
login = json.load(open(os.path.dirname(os.path.realpath(__file__)) + "/.login"))

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
    else:
      return {"type": "transfer"}
  
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
  print "==== updating", account, datetime.now().year, "====\n"

  tabs = "\t" * (len(account) / 2)

  # log in
  print "starting scraper...",
  td = tdapi.TD(login)
  print tabs + "done"

  # switch account to IRA
  print "switching to " + account + "...",
  td.account(account)
  print "\t\tdone"

  # get transaction history
  print "getting history...",
  history = td.history()
  parsed = parse_history(history)
  print tabs + "\tdone"

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
    print "getting $" + s.upper() + " data...",
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
    print tabs + "done" if len(s) < 4 else tabs[:-1] + "done"

  # quit
  print "exiting scraper...",
  td.close()
  print tabs + "\tdone"

  print "saving data...",
  files = []
  files.append(save_data("tda_" + account + "_" + str(datetime.now().year), ".json", datafolder, parsed))
  for s in symboldata:
    files.append(save_data(s["symbol"], ".txt", datafolder, s["data"]))

  print tabs + "\t\t\tdone\n"

  for f in files:
    print f

  print "\n==== updated data ===="
  return file