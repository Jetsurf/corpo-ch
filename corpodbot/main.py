import sys, os, discord, asyncio, time, json, logging

sys.path.append('..')
#Django
import django
import django.db
from django.conf import settings
from django.utils import timezone

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'DiscordOauth2.settings'
)

from dotenv import load_dotenv

dirname = os.path.dirname(sys.argv[0]) or '.'
sys.path.append(f"{dirname}/modules")

#loadConfig()
class CorpoDbot(discord.Bot):
	def __init__(self):
		django.setup()
		load_dotenv("../.env")
		intents = discord.Intents.default()
		intents.members = True
		self.client = super().__init__(intents=intents, chunk_guilds_at_startup=False)

		# cogs
		cogList = [
			#'fun',
			#'chcmds',
			'tourneycmds',
			#'qualifiercmds'
			'ownercmds'
		]

		for cog in cogList:
			self.load_extension(f'cogs.{cog}')
			print(f'Cog loaded: {cog}')

		self.owners = []
		self.proofCalls = None
		
	def run(self):
		self.startUpLogging()
		print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
		print('Logging into discord')
		super().run(os.getenv("client_token"), reconnect=True)

		print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")

	def startUpLogging(self):
		#if configData.get('output_to_log'):
		#os.makedirs(f"{dirname}/logs", exist_ok=True)
		#sys.stdout = open(f"{dirname}/logs/discordbot.log", 'a+')
		sys.stdout.reconfigure(line_buffering = True)
		#sys.stderr = open(f"{dirname}/logs/discordbot.err", 'a+')
		sys.stderr.reconfigure(line_buffering = True)

	async def retrieveOwners(self):
		print("Retrieving bot owners...")
		app = await self.application_info()
		if app.team:
			for mem in app.team.members:
				owner = await self.fetch_user(mem.id)
				if not owner:
					print(f"  Can't get user object for team member {str(mem.name)}#{str(mem.discriminator)} id {mem.id}")
				else:
					self.owners.append(owner)
					print(f"  Loaded owner: {str(owner.name)} id {owner.id}")
		else:
			self.owners = [app.owner]
			print(f"  Loaded owner: {str(app.owner.name)} id {app.owner.id}")

	async def on_ready(self, once=True):
		print(f"Logged in as {self.user.name}#{self.user.discriminator} id {self.user.id}")

		await self.retrieveOwners()
		#await client.tourneyDB.loadMatches()
		print("Checking Proofcalls")
		#self.proofCalls = proofcalls.ProofCalls(self)
		#await self.proofCalls.init()

		print('------Done with Startup------')

if __name__ == "__main__":
	bot = CorpoDbot()
	bot.run()
