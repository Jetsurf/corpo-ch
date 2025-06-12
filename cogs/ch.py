import discord, requests, os, sys, json
from discord.ext import commands

class ch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # CHOpt path
        dirname = os.path.dirname(sys.argv[0]) or '.'
        self.CHOptPath = f'{dirname}/../CHOpt'

        # enchor.us API urls
        self.enchor={}
        self.enchor['gen'] = 'https://api.enchor.us/search'
        self.enchor['adv'] = 'https://api.enchor.us/search/advanced'
        self.enchor['dl'] = 'https://files.enchor.us/'
    
    def CHOpt(self, chart: str):
        return
    
    def encorSearch(self, query: dict):
        d = {'number':1,
                'page':1}
        
        for i in query:
            d[i]={'value':query[i],'exact':False,'exclude':False}
        
        print(d)
        resp = requests.post(self.enchor['adv']
            ,data=json.dumps(d)
            ,headers={"Content-Type":"application/json"})
        
        print(resp.json())
        s={}
        d=resp.json()['data'][0]
        atts=['name','artist','md5','charter','album','hasVideoBackground']
        
        for i in atts:
            s[i]=d[i]
        return s
    
    def enchorDownload(self, url: str):
        return
    
    ch = discord.SlashCommandGroup('ch','CloneHero tools')
    @ch.command(name='path',description='Generate a path for a given chart on Chorus')
    async def path(self, ctx, name: str, artist: str = None, charter: str = None, album: str = None):
        qList=['name','artist','charter','album']
        query={}

        for i,a in locals().items():
            if (i in qList and a != None):
                query[i]=a
        print(query)
        s=self.encorSearch(query)

        # form download url
        url=self.enchor['dl'] + s['md5'] + ('_novideo','')[not s['hasVideoBackground']] + '.sng'
        enchorDownload(url)
#https://www.enchor.us/download?md5=ce60a1df07f48526d68568fa73a4fc56&isSng=false&downloadNovideoVersion=false&filename=Cordova%2520-%2520Alive%2520%28QwertyBurger%29
#https://www.enchor.us/download?md5=d92a3e7e40e733831ebc9f9606dc5a14&isSng=false&downloadNovideoVersion=false&filename=Insomnium%2520-%2520Heart%2520Like%2520a%2520Grave%2520%28K4JK0%29
#https://files.enchor.us/${md5 + (downloadNovideoVersion ? '_novideo' : '')}.sng

        print(url)
        await ctx.respond(url)


def setup(bot):
    bot.add_cog(ch(bot))
