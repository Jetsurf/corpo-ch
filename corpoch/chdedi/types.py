import pydantic, socket, typing

from pydantic import Field

SERVER_CONFIG_CHOICES = (
	("disabled", "Disabled"),
	("open", "Open"),
	("tournament", "Tournament"),
)

class CHRedisSettings(pydantic.BaseModel):
	redis_enable : int = Field(0, ge=0, le=1)
	redis_db_id : int = Field(0, ge=0, le=100)
	redis_password : str = ""
	redis_hostname : str = "localhost"

class CHServerSettings(pydantic.BaseModel):
	minrequiredplayers : int = Field(1, ge=1, le=4)
	maxplayers : int = Field(2, ge=2, le=4)
	onlyhostchoosesongs : int = Field(0, ge=0, le=1)
	maxspectators : int = Field(4, ge=0, le=20)
	servertickrate : int = Field(120, ge=30, le=1000)
	lowsongspeed : int = Field(25, ge=25, le=100)
	maxsongspeed : int = Field(500, ge=100, le=5000)
	clientremovesongs : int = Field(1, ge=0, le=1)
	songsperclient : int = Field(1, ge=0, le=1)

class CHServerSpecificSettings(pydantic.BaseModel):
	name : str = "Corpo CH - Dedicated Server"
	port : int = Field(14242, ge=1024, le=65534)
	ip : str = socket.gethostbyname(socket.gethostname())
	password: str = ""

class CHListenerSettings(pydantic.BaseModel):
	udp_events_host : str = "127.0.0.1" #Keeping this localhost entirely for now
	udp_events_port : int = Field(14300, ge=1024, le=65534)
	udp_events_enable : int = Field(1, ge=0, le=1)

class CHOnlineSettings(CHServerSettings, CHServerSpecificSettings, CHListenerSettings):
	pass

class CHSettings(pydantic.BaseModel):
	redis: CHRedisSettings
	online: CHOnlineSettings
	udpevents: CHListenerSettings
