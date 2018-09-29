from os.path import isfile, join, realpath, dirname
from tdascraper import update_td
from datetime import datetime, timedelta
from copy import deepcopy
import pexpect
import time
import json
import os

RUN_UPDATE = True
DELETE_DATA_AFTER = True

OUTPUT_DATA = os.path.join(dirname(realpath(__file__))) + "/datadumps"
ACCOUNTS = json.load(open(dirname(realpath(__file__)) + "/accounts.json"))
ADJUSTMENTS = json.load(open(os.path.dirname(os.path.realpath(__file__)) + "/adjustments.json"))
LOGIN = json.load(open(dirname(realpath(__file__)) + "/.login"))
DATA_FOLDER = "./datadumps"
TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
DATE_FORMAT = "%m/%d/%Y"
DATA_FILES = [f for f in os.listdir(DATA_FOLDER) if isfile(join(DATA_FOLDER, f))]
TDA_FILES = [f for f in DATA_FILES if "tda_" in f]

# update all accounts
# TODO: make tdascraper an object you can keep instances of and switch accounts for
# OR make it take an array of accounts to iterate through to update
def getdata():
  for a in ACCOUNTS:
    update_td(a, DATA_FOLDER)

def makedata(account):
  # get all transactions
  year = datetime.now().year
  transactions = []
  readfile = "_".join(map(str, ["tda",account,year])) + ".json"
  while readfile in TDA_FILES:
    with open(DATA_FOLDER + "/" + readfile) as f:
      transactions += json.load(f)
    readfile = readfile.replace(str(year), str(year-1))
    year -= 1

  # get basic statistics and remap data to transaction dates
  symbols_traded = []
  transaction_map = {}
  startdate = None
  for t in transactions:
    date = datetime.strptime(t["date"], TIME_FORMAT)
    datestr = date.strftime(DATE_FORMAT)
    if not startdate or date < startdate: startdate = date
    if "symbol" in t and t["symbol"] not in symbols_traded: symbols_traded.append(t["symbol"])
    if datestr in transaction_map: transaction_map[datestr].append(t)
    else: transaction_map[datestr] = [t]

  # get symbol data
  history = {}
  for s in symbols_traded:
    with open(DATA_FOLDER + "/" + s + ".txt") as f:
      history[s] = json.load(f)
  
  # apply timeseries data
  timeseries = {
    "meta": {
      "start_date": startdate.strftime(DATE_FORMAT),
      "last_updated": datetime.now().strftime(DATE_FORMAT),
      "adjustment_history": ADJUSTMENTS,
      "symbols_traded": symbols_traded,
      "max_contribution": 5500,
      "commission": [
        ["2/28/2018", 6.95]
      ]
    }
  }
  day = startdate
  today = datetime.now()
  active_investments = []
  positions = {}
  total_contributions = 0
  ytd_contributions = {str(startdate.year): 0}
  total_fees = 0
  cash_balance = 0
  while day < today:
    if day.weekday() < 5:
      daystr = day.strftime(DATE_FORMAT)
      data = {}
      
      # check for contributions or updates to positions
      transactions = transaction_map[daystr] if daystr in transaction_map else []
      latest = None

      # update positions
      data["positions"] = positions
      for p in data["positions"]:
        pos = data["positions"][p]
        # do not update if holiday or missing info
        if daystr not in history[p]: break
        pos["o"] = history[p][daystr]["o"]
        pos["h"] = history[p][daystr]["h"]
        pos["l"] = history[p][daystr]["l"]
        pos["c"] = history[p][daystr]["c"]
        # ajdust position info to if needed:
        # - stock prices before splits/adjustments are reverted to original
        # - avg + shares are adjusted on day of splits/adjustments, carried forward
        if p in ADJUSTMENTS:
          adj = ADJUSTMENTS[p]
          # if day of adjusment, ajust shares + avg
          if daystr in adj:
            ratio = float(adj[daystr]["ratio"].split(":")[0])/float(adj[daystr]["ratio"].split(":")[1])
            pos["avg"] /= ratio
            pos["shares"] = int(round(pos["shares"] * ratio))
          else:
            adjday = today # datetime objects are immutable
            while adjday > day:
              adjstr = adjday.strftime(DATE_FORMAT)
              if adjstr in adj and adj[adjstr]["kibot_updated"]:
                ratio = float(adj[adjstr]["ratio"].split(":")[0])/float(adj[adjstr]["ratio"].split(":")[1])
                for key in ["o","h","l","c"]:
                  pos[key] *= ratio
              adjday -= timedelta(days=1)

      # update transactions, and positions
      if len(transactions) > 0: data["transactions"] = transactions
      for t in transactions:
        current = datetime.strptime(t["date"], TIME_FORMAT)

        if t["type"] == "transfer":
          total_contributions += t["amount"]
          if str(day.year) in ytd_contributions: ytd_contributions[str(day.year)] += t["amount"]
          else: ytd_contributions[str(day.year)] = t["amount"]
        elif t["type"] == "fee":
          total_fees += abs(t["amount"])
        # elif t["type"] == "adj":
          # continue
        elif t["type"] in ["buy", "sell"]:
          sym = t["symbol"]
          hist = history[sym][daystr]
          if t["type"] in ["buy", "sell"]:
            commissions = timeseries["meta"]["commission"]
            currCommission = commissions[-1][1]
            if datetime.strptime(commissions[-1][0], DATE_FORMAT) > day:
              commissionsIndex = -1
              while abs(commissionsIndex) <= len(commissions) and datetime.strptime(commissions[commissionsIndex][0], DATE_FORMAT) > day:
                commissionsIndex -= 1
              currCommission = commissions[commissionsIndex][1]

        if t["type"] == "buy":
          total_fees += currCommission
          # new position
          if sym not in active_investments:
            active_investments.append(sym)
            data["positions"][sym] = {
              "shares": t["shares"],
              "o": hist["o"],
              "h": hist["h"],
              "l": hist["l"],
              "c": hist["c"],
              "avg": t["price"],
              "since": t["date"],
            }
            # adjust stock prices for future splits/adjustments
            if sym in ADJUSTMENTS:
              adj = ADJUSTMENTS[sym]
              adjday = today # datetime objects are immutable
              while adjday > day:
                adjstr = adjday.strftime(DATE_FORMAT)
                if adjstr in adj and adj[adjstr]["kibot_updated"]:
                  ratio = float(adj[adjstr]["ratio"].split(":")[0])/float(adj[adjstr]["ratio"].split(":")[1])
                  for key in ["o","h","l","c"]:
                    data["positions"][sym][key] *= ratio
                adjday -= timedelta(days=1)
          # updated position
          else:
            pos = data["positions"][sym]
            pos["avg"] = ((pos["avg"] * pos["shares"]) + (t["shares"] * t["price"])) / (pos["shares"] + t["shares"])
            pos["shares"] += t["shares"]

        if t["type"] == "sell":
          total_fees += currCommission
          pos = data["positions"][sym]
          if pos["shares"] == t["shares"]:
            active_investments.remove(sym)
            data["positions"].pop(sym, None)
          else:
            pos["shares"] -= t["shares"]

        if latest is None or latest <= current: cash_balance = t["remaining"]
        latest = current

      # update account information
      data["total_contributions"] = total_contributions
      data["ytd_contributions"] = ytd_contributions[str(day.year)]
      data["cash_balance"] = cash_balance
      data["active_investments"] = active_investments[:]
      data["total_fees"] = total_fees
      data["balance"] = data["cash_balance"] + sum([data["positions"][p]["shares"] * data["positions"][p]["c"] for p in data["positions"]])

      timeseries[daystr] = data
      # deepcopy local positions
      positions = deepcopy(data["positions"])
    day += timedelta(days=1)

  return timeseries

def savedata(data, encrypted=False):
  file = OUTPUT_DATA + "/deltapoint.appdata" + (".encrypted" if encrypted else "") + ".json"
  f = open(file, "w")
  f.write(json.dumps(data, indent=2))
  return file

def senddata(file):
  file = file.replace(' ','\ ')
  child = pexpect.spawn(' '.join(['scp -P',LOGIN["scp_port"],file,LOGIN["scp_addr"]]))
  child.expect(".*password.*")
  child.sendline(LOGIN["scp_pwd"])
  child.read()

if RUN_UPDATE: 
  getdata()
  DATA_FILES = [f for f in os.listdir(DATA_FOLDER) if isfile(join(DATA_FOLDER, f))]
  TDA_FILES = [f for f in DATA_FILES if "tda_" in f]
  print ""

accountdata = {}
for a in ACCOUNTS:
  print "building "+a+"...",
  accountdata[a] = makedata(a)
  print ("\t" * (len(a) / 3)) + "done"
  
print "saving to file...",
f = savedata(accountdata)
print ("\t" * (len(a) / 3)) + "\t\t\t\tdone"

print "encrypting file...",
os.system(' '.join(["staticrypt", f.replace(' ','\ '), LOGIN["scp_pwd"]]))
time.sleep(1)
with open("datadumps/deltapoint.appdata.json_encrypted.html", "r") as file:
  for line in file.readlines():
    if "encryptedMsg = '" in line.strip(): 
      f = savedata({"encryptedMsg": line.strip()[16:-2]}, True)
      break
print ("\t" * (len(a) / 3)) + "\t\t\t\tdone"

if RUN_UPDATE: 
  print "uploading to server...",
  senddata(f)
  print ("\t" * (len(a) / 3)) + "\t\tdone"
