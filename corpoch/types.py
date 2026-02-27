import pydantic, typing
from datetime import datetime

CH_MODIFIERS = (
	("NM", "No Modifiers"),
	("AH", "All Hopos"),
	("AS", "All Strums"),
	("AT", "All Taps"),
	("AO", "All Opens"),
	("BM", "Brutal Mode"),
	("DD", "Deadly Dynamics"),
	("DN", "Double Notes"),
	("DS", "Dropless Sustains"),
	("PM", "Precision Mode"),
	("NS", "Note Shuffle"),
	("DK", "Double Kick"),
	("NK", "No Kick"),
)

CH_VERSIONS = (
	("v1.0.0.4080-final", "v1.0.0.4080-final"),
)

CH_INSTRUMENTS = (
	("guitar", "Guitar"),
	("coop", "Guitar Coop"),
	("bass", "Bass"),
	("rhythm", "Rhythm"),
	("keys", "Keys"),
	("drums", "Drums"),
	("ghl", "GHL Guitar"),
	("ghlbass", "GHL Bass"),
	("ghlrythm", "GHL Rhythm"),
	("ghlcoop", "GHL Guitar Coop"),
)

CH_DIFFICULTIES = (
	("expert", "Expert"),
	("hard", "Hard"),
	("medium", "Medium"),
	("easy", "Easy"),
)

CHART_CATEGORIES = (
	("none", "None"),
	("hybrid", "Hybrid"),
	("fret", "Fret"),
	("strum", "Strum"),
	("sprint", "Sprint"),
	("marathon", "Marathon"),
)

TB_RULESETS = (
	("single", "Single TB"),
	("csc", "CSC TB Rules"),
	("banpick", "'NPDO' Ban/Pick"),
	('refdecide', "Ref picks from unplayed"),
)

PICK_RULESETS = (
	("loserpicks", "High Seed 1st Pick/Loser Picks"),
	("alternate", "Alternate player picks"),
)

BAN_RULESETS = (
	("default", "No Defer/High Seed first"),
	("deferban", "High Seed can defer ban/picks first"),
	("deferboth", "High Seed can defers both ban/pick"),
)

#This is for v6 steg
class StegScreenshotPlayer(pydantic.BaseModel):
	accent_notes_hit : int = 0
	accent_notes_total : int = 0
	audio_calibration : float = 0
	base_score : int = 0
	controller_type : str
	difficulty : str = "Expert"
	frets_ghosted : int = 0
	gamepad_mode : bool = False
	ghost_notes_hit : int = 0
	ghost_notes_total : int = 0
	instrument : str = "Guitar"
	is_bot : bool = False
	is_fc : bool = False
	lefty_flip : bool = False
	max_streak : int = 0
	modifiers :  list = ['NoModifiers']
	no_fail : bool = False
	notes_hit : int = 0
	profile_name : str = "Some Player"
	remote_network_player : bool = False
	score : int = 0 
	solo_bonus_total : int = 0
	sp_phrases_earned : int = 0
	sp_phrases_total : int = 0
	total_notes : int = 0
	versus_winner : bool = False
	video_calibration : float = 0
	excess_hits : int = 0
	notes_missed : int = 0

class StegScreenshot(pydantic.BaseModel):
	artist_name : typing.Optional[str] = "None"
	band_score : typing.Optional[int] = 0
	band_stars : typing.Optional[int] = 0
	checksum : typing.Optional[str] = "None"
	charter_name : typing.Optional[str] = "None"
	game_version : typing.Optional[str] = CH_VERSIONS[0]
	game_mode : typing.Optional[str] = "Versus"
	playback_speed : typing.Optional[int] = 100
	players : typing.Optional[list[StegScreenshotPlayer]] = []
	score_timestamp: typing.Optional[datetime] = datetime.now()
