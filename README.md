# deltapoint-scraper
A scraper for TD Ameritrade that retrieves all transactions and creates a daily historic account overview

### Adding scraper to launchd
In order to have the scraper run automatically every night, follow these steps:

1) In a file called `launchd.sh` add the following lines. Save to same root directory as scraper's `main.py`.

```
# source ~/.bashrc
# cd /Users/[USER]/PATH/TO/deltapoint-scraper
# /Users/[USER]/PATH/TO/deltapoint-scraper/runpy.sh
```

2) In `com.deltapoint.tda.scraper.plist` file, update the two address `<string>` tags with the absolute address to the scraper.

3) Find the folder for launchd `.plist` files. Probably located `~/Library/LaunchAgents/`. Copy the included `com.deltapoint.tda.scraper.plist` file to that folder.

4) In terminal, run the following command to load the file:

```
launchctl load ~/Library/LaunchAgents/com.deltapoint.tda.scraper.plist
```

If you need to unload the task, run 
```
launchctl unload ~/Library/LaunchAgents/com.deltapoint.tda.scraper.plist
```