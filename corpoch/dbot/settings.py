import os, sys
from dotenv import load_dotenv
#This is still stupid - what's wrong?
sys.path.append('../../')
load_dotenv('../../')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")
