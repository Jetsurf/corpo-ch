import sys, os
#import logging
#logging.basicConfig(level=logging.DEBUG)

dirname = os.path.dirname(sys.argv[0]) or '.'
sys.path.append(f"{dirname}/modules")

import discord, asyncio, time, json

import mysqlhandler

intents = discord.Intents.default()
intents.members = True
client = discord.Bot(intents=intents, chunk_guilds_at_startup=False)

# cogs
cogList = [
	'fun',
	'chcmds',
	'tourneycmds'
]

for cog in cogList:
	client.load_extension(f'cogs.{cog}')
	print(f'Cog loaded: {cog}')

owners = []
doneStartup = False
configData = None
mysqlHandler = None

def loadConfig():
	global configData
	try:
		with open(f"{dirname}/config/bot.json", 'r') as json_config:
			configData = json.load(json_config)

		print('Config Loaded')
	except Exception as e:
		print(f"Failed to load config: {str(e)}")
		quit(1)

def startUpDB():
	global configData, mysqlHandler, client

	mysqlHandler = mysqlhandler.mysqlHandler(configData['mysql_host'], configData['mysql_user'], configData['mysql_pw'], configData['mysql_db'])

	# Get the secrets the F out!
	configData['mysql_host'] = None
	configData['mysql_user'] = None
	configData['mysql_pw'] = None
	configData['mysql_db'] = None

	client.loop.create_task(startUpDBAsync())

async def startUpDBAsync():
	global mysqlHandler

	await mysqlHandler.startUp()

	#mysqlSchema = mysqlschema.MysqlSchema(mysqlHandler)
	#await mysqlSchema.update()

async def retrieveOwners():
	global client, owners

	owners = []
	print("Retrieving bot owners...")

	app = await client.application_info()  # Get owners from Discord team api
	if app.team:
		for mem in app.team.members:
			owner = await client.fetch_user(mem.id)
			if not owner:
				print(f"  Can't get user object for team member {str(mem.name)}#{str(mem.discriminator)} id {mem.id}")
			else:
				owners.append(owner)
	else:
		owners = [app.owner]

	for owner in owners:
		print(f"  Loaded owner: {str(owner.name)} id {owner.id}")

	return

@client.event
async def on_ready():
	global client, doneStartup

	if not doneStartup:
		print(f"Logged in as {client.user.name}#{client.user.discriminator} id {client.user.id}")
		await retrieveOwners()
	else:
		print("RECONNECT TO DISCORD")

	print('------Done with Startup------')
	doneStartup = True

loadConfig()
startUpDB()
print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
print('Logging into discord')

token = configData['token']
configData['token'] = ""

client.run(token)

print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
