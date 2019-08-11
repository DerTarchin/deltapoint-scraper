from os.path import isfile, join, realpath, dirname
import math
import traceback
from datetime import datetime, timedelta
from shutil import copyfile
import os
import sys
import time

def printf(txt):
  LOG = open(dirname(realpath(__file__)) + "/log.txt", "a")
  print txt,
  LOG.write(txt)
  LOG.flush()

try:
  # printf("running..." + datetime.now().strftime("%m/%d/%Y %H:%M:%S")+"\n")
  # printf(os.getcwd()+"\n")
  # printf(dirname(realpath(__file__))+"\n")

  # special imports
  from tdascraper import update_td
  from copy import deepcopy
  import pexpect
  import json

  # sys.exit();

  RUN_UPDATE = True
  SEND_DATA = True

  CWD = dirname(realpath(__file__))
  DATA_FOLDER = os.path.join(CWD) + "/datadumps"
  ACCOUNTS = json.load(open(CWD + "/accounts.json"))
  ADJUSTMENTS = json.load(open(CWD + "/adjustments.json"))
  LOGIN = json.load(open(CWD + "/.login"))
  TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
  DATE_FORMAT = "%m/%d/%Y"
  FILENAME_LONG = "deltapoint.appdata.json"
  FILENAME = ".dpd"

  YEAR = datetime.now().year
  # YEAR = 2018

  # update all accounts
  # TODO: make tdascraper an object you can keep instances of and switch accounts for
  # OR make it take an array of accounts to iterate through to update
  def getdata():
    for a in ACCOUNTS:
      update_td(a, DATA_FOLDER, YEAR)

  def makedata(account):
    global YEAR
    # get all transactions
    transactions = []
    readfile = "_".join(map(str, ["tda", account, YEAR])) + ".json"
    while readfile in TDA_FILES:
      with open(DATA_FOLDER + "/" + readfile) as f:
        transactions += json.load(f)
      readfile = readfile.replace(str(YEAR), str(YEAR-1))
      YEAR -= 1

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
        "adjustment_history": ADJUSTMENTS["adjustment_history"],
        "symbols_traded": symbols_traded,
        "max_contribution": ADJUSTMENTS["contribution_history"],
        "commission": ADJUSTMENTS["commission_history"]
      }
    }
    day = startdate
    today = datetime.now()
    active_investments = []
    positions = {}
    total_contributions = 0
    ytd_contributions = { str(startdate.year): 0 }
    total_fees = 0
    cash_balance = 0
    total_trades = 0
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
          # - avg + shares are adjusted on day of splits/adjustments, carried forward
          if p in ADJUSTMENTS["adjustment_history"]:
            adj = ADJUSTMENTS["adjustment_history"][p]
            # if day of adjusment, ajust shares + avg
            if daystr in adj:
              ratio = float(adj[daystr]["ratio"].split(":")[0])/float(adj[daystr]["ratio"].split(":")[1])
              pos["avg"] /= ratio
              pos["shares"] = int(math.floor(pos["shares"] * ratio))
            else:
              adjday = today # datetime objects are immutable
              ratio = None
              while ratio is None and adjday >= startdate:
                adjstr = adjday.strftime(DATE_FORMAT)
                if adjstr in adj and not adj[adjstr]["kibot_updated"]:
                  ratio = float(adj[adjstr]["ratio"].split(":")[0])/float(adj[adjstr]["ratio"].split(":")[1])
                else:
                  adjday -= timedelta(days=1)
              if adjday < day and ratio:
                for key in ["o","h","l","c"]:
                  pos[key] /= ratio

        # update transactions, and positions
        if len(transactions) > 0: data["transactions"] = transactions
        for t in transactions:
          current = datetime.strptime(t["date"], TIME_FORMAT)

          cash_balance += t["amount"]

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
            # >> following was removed due to introduction of commission in data
            # commissions = timeseries["meta"]["commission"]
            # currCommission = commissions[-1][1]
            # if datetime.strptime(commissions[-1][0], DATE_FORMAT) > day:
            #   commissionsIndex = -1
            #   while abs(commissionsIndex) <= len(commissions) and datetime.strptime(commissions[commissionsIndex][0], DATE_FORMAT) > day:
            #     commissionsIndex -= 1
            #   currCommission = commissions[commissionsIndex][1]
            total_fees += t["commission"]
            total_fees += t["reg_fee"]
            total_trades += 1

          if t["type"] == "buy":
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
            pos = data["positions"][sym]
            if pos["shares"] == t["shares"]:
              active_investments.remove(sym)
              data["positions"].pop(sym, None)
            else:
              pos["shares"] -= t["shares"]

          latest = current

        # update account information
        data["total_contributions"] = total_contributions
        data["ytd_contributions"] = ytd_contributions.get(str(day.year), 0)
        data["cash_balance"] = cash_balance
        data["total_fees"] = total_fees
        data["balance"] = data["cash_balance"] + sum([data["positions"][p]["shares"] * data["positions"][p]["c"] for p in data["positions"]])
        data["total_trades"] = total_trades

        timeseries[daystr] = data
        # deepcopy local positions
        positions = deepcopy(data["positions"])
      day += timedelta(days=1)

    return timeseries

  def savedata(data, encrypted=False):
    if encrypted:
      file = DATA_FOLDER + "/" + FILENAME
    else:
      file = DATA_FOLDER + "/" + FILENAME_LONG
    f = open(file, "w")
    f.write(json.dumps(data, indent=2))
    return file

  def senddata(file):
    copyfile(file, LOGIN["repo"] + FILENAME)
    child = pexpect.spawn("bash")
    child.sendline("cd " + LOGIN["repo"])
    child.sendline("git add .;git commit -m refresh;git push origin master")
    child.readline() # use print to see errors
    child.sendline("exit")
    child.read()

  ############# MAIN #############
  printf("\n\n==== " + datetime.now().strftime(TIME_FORMAT) + " ====\n")

  if RUN_UPDATE: 
    getdata()

  DATA_FILES = [f for f in os.listdir(DATA_FOLDER) if isfile(join(DATA_FOLDER, f))]
  TDA_FILES = [f for f in DATA_FILES if "tda_" in f]
  accountdata = {}
  for a in ACCOUNTS:
    printf( "building "+a+"...")
    accountdata[a] = makedata(a)
    printf( "done\n")
    
  printf( "saving to file...")
  f = savedata(accountdata)
  printf("done\n")

  printf( "encrypting file...")
  os.system(' '.join(["staticrypt", f.replace(' ','\ '), LOGIN["pwd"]]))
  time.sleep(1)
  with open(DATA_FOLDER+"/" + FILENAME_LONG + "_encrypted.html", "r") as file:
    for line in file.readlines():
      if "encryptedMsg = '" in line.strip(): 
        f = savedata({"encryptedMsg": line.strip()[16:-2]}, True)
        break
  printf("done\n")

  if SEND_DATA:
    printf( "uploading to server...")
    senddata(f)
    printf( "done\n")
  else:
    printf("Skipped sending to server.")
  printf( "=============================")

except Exception, e:
    traceback.print_exc()
    printf(str(e) + "\n")