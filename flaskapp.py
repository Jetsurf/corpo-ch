import json, requests, time, sys, base64, asyncio, datetime, os, uuid
from flask import Flask, request, Response, url_for

sys.path.append(f"./modules")

import tourneysql
import mysqlhandler

app = Flask(__name__)
configData = None
mysqlh = None
sql = None
doneStartup = False 

def load_config():
	global configData
	try:
		with open('./config/bot.json', 'r') as json_config:
			configData = json.load(json_config)
	except:
		print("Error opening/parsing config")
		sys.quit(1)
		print("Config Loaded")

	return configData

def startUpLogging():
	if configData.get('output_to_log'):
		os.makedirs(f"{dirname}/logs", exist_ok=True)
		sys.stdout = open(f"{dirname}/logs/discordbot.log", 'a+')
		sys.stdout.reconfigure(line_buffering = True)
		sys.stderr = open(f"{dirname}/logs/discordbot.err", 'a+')
		sys.stderr.reconfigure(line_buffering = True)

async def startUpDBAsync():
	global configData, mysqlh, sql

	try:
		await mysqlh.close_pool()
	except:
		pass

	mysqlh = mysqlhandler.mysqlHandler(configData['mysql_host'], configData['mysql_user'], configData['mysql_pw'], configData['mysql_db'])
	await mysqlh.startUp()
	sql = tourneysql.TourneyDB(None, mysqlh)

@app.route("/", methods=["POST"])
async def update_match():
	global sql
	await startUpDBAsync()
	mjson = json.loads(request.data.decode("utf-8"))
	if 'api_key' in request.headers and request.headers['Api-Key'] == "3de230bc27d44bcc9c9b59830bbe2e5c" and 'uuid' in mjson:
		#Use hard coded tid for BWS - Need to get actual setlist from DB for specific tourney
		#try:
		if mjson['endTime'] == None:
			match = await sql.getRefToolMatch(mjson['uuid'])
			await sql.replaceRefToolMatch(mjson['uuid'], 1, False, mjson, match['sheetrow'])
			print(f"Updated match {mjson['uuid']} for {request.headers['X-Real-Ip']}")
		else:
			await sql.replaceRefToolMatch(mjson['uuid'], 1, True, mjson)
			print(f"FINISHED match {mjson['uuid']} for {request.headers['X-Real-Ip']} with times {mjson['startTime']} to {mjson['endTime']}")
		
		return "1", 200
		#except:
		#	print(f"FAILURE to update match {mjson['uuid']} for {request.headers['X-Real-Ip']}")
		#	return "0", 500
	else:
		return Response(), 403

@app.route("/", methods=["GET"])
async def setup_reftool():
	global sql
	await startUpDBAsync()
	if 'api_key' in request.headers and request.headers['Api-Key'] == "3de230bc27d44bcc9c9b59830bbe2e5c":
		muuid = str(uuid.uuid1())
		await sql.replaceRefToolMatch(muuid, 1, False, {'uuid' : muuid})
		print(f"Added match {muuid} for {request.headers['X-Real-Ip']}")
		return muuid, 200
	else:
		return Response(), 403

s = requests.Session()
config_data = load_config()
startUpLogging()

if __name__ == '__main__':
		app = Flask(__name__)
		#SCRIPT_NAME=/tdx-posim
		app.config['PATH'] = "/home/dbot/corp-bot-dev"
		app.config['SERVER_NAME'] = 'reftool.corpo-ch.org'
		app.config['SCRIPT_NAME'] = '/'
		#print(f"Setting app path {config_data['app_root']}")
		print("Loading Flask")
		app.run(host='127.0.0.1', port=8010, debug=True)
