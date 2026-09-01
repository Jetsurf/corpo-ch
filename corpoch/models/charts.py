import io

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from multiselectfield import MultiSelectField
from polymorphic.models import PolymorphicModel

from corpoch.utils.snghandler import SNGHandler
from corpoch.types import CH_INSTRUMENTS, CH_DIFFICULTIES, CH_MODIFIERS, CH_VERSIONS, CHART_CATEGORIES
from corpoch.validators import validate_chart_file

class CHIcon(models.Model):
	"""
	Represents an Icon for a chart used in a Tournament. 
	"""
	name = models.CharField(verbose_name="Name", blank=False, max_length=32, default="newicon", primary_key=True, help_text="The icon name.")
	img = models.ImageField(upload_to="chicons/", verbose_name="Image", null=True, blank=True, help_text="URL of the chart icon.")

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"
		app_label = 'corpoch'

	def __str__(self):
		return self.name

	@property
	def emote(self):
		return self.discord if self.discord else None

class Chart(PolymorphicModel):
	"""
	Represents a Chart for a Bracket setlist or Qualifier. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a chart.")
	name = models.CharField(verbose_name="Chart Name", max_length=256, blank=True, help_text="Name of the chart.")
	artist = models.CharField(verbose_name="Artist", max_length=256, blank=True, help_text="Artist of the song.")
	album = models.CharField(verbose_name="Album", max_length=256, blank=True, help_text="Album the song is from.")
	charter = models.CharField(verbose_name="Charter", max_length=64, blank=True, help_text="Author of a chart.")
	boss = models.BooleanField(verbose_name="Boss Song", default=False, help_text="Is chart a 'boss' song.")
	tiebreaker = models.BooleanField(verbose_name="Tiebreaker", default=False, help_text="Is this chart a tiebreaker in a setlist.")
	difficulty = models.CharField(verbose_name="Difficulty", choices=CH_DIFFICULTIES, max_length=16, default=CH_DIFFICULTIES[0][0], help_text="Difficulty this chart is to be played on.")
	instrument = models.CharField(verbose_name="Instrument", choices=CH_INSTRUMENTS, max_length=32, default=CH_INSTRUMENTS[0][0])
	modifiers = MultiSelectField("Modifiers", choices=CH_MODIFIERS, default=CH_MODIFIERS[0][0], help_text="Modifiers expected to be used.")
	speed = models.PositiveIntegerField(verbose_name="Speed", validators=[MinValueValidator(5), MaxValueValidator(1000)], default=100, help_text="Expected playback speed.")
	category = models.CharField(verbose_name="Chart Category", choices=CHART_CATEGORIES, max_length=16, default=CHART_CATEGORIES[0][0])#This needs to be choices
	brackets = models.ManyToManyField("Bracket", related_name="setlist", verbose_name="Bracket Setlist", blank=True, help_text="Bracket setlists this chart is used in.")
	md5 = models.CharField(verbose_name="MD5 Hash", max_length=32, blank=True, help_text="The md5sum of the notes.chart/mid file. Used for steg verification.")
	blake3 = models.CharField(verbose_name="Blake3 Hash", max_length=32, blank=True, help_text="The Encore blake3 hash for a chart to import.")
	url = models.URLField(verbose_name="Chart URL", blank=True, help_text="URL this chart is available at.")
	icon = models.ForeignKey(CHIcon, related_name="charts", verbose_name="CH Icon", null=True, blank=True, on_delete=models.SET_NULL, help_text="The in-game setlist icon for the chart.")
	sngfile = models.FileField(upload_to="sngfiles/", validators=[validate_chart_file], verbose_name="SNG File", null=True, blank=True, help_text="The chart file. Stored as .sng but available as old .chart format.")

	class Meta:
		verbose_name = "Chart"
		verbose_name_plural = "Charts"

	@property
	def long_name(self):
		return f"{self.name} - {self.charter} - {self.artist} - {self.album}{f' -{self.instrument[1]}' if self.instrument[0] != 'guitar' else ''}{f' {self.difficulty[1]}' if self.difficulty[0] != 'expert' else ''}"

	@property
	def encore_search_query(self):
		return { 'name' : self.name, 'charter' : self.charter, 'artist' : self.artist, 'album' : self.album, 'instrument': self.instrument, 'difficulty' : self.difficulty, 'blake3' : self.blake3 }

	# These modifiers could be made better. Not sure quite yet on how the 0 index in the types should be defined back to here as class vars
	@property
	def modifiers_short(self):
		outStr = ""
		if self.modifiers[0] != "NM":
			for i, mod in enumerate(self.modifiers):
				if i == 0:
					outStr += mod
				else:
					outStr += f" {mod}"

		return outStr

	@property
	def modifiers_long(self):
		return " ".join(self.modifiers_list)

	@property
	def modifiers_list(self) -> list:
		out = []
		for i in range(0, len(self.modifiers)):
			for mod in CH_MODIFIERS:
				if mod[0] == self.modifiers[i]:
					out.append(mod[1])
		return out

	@property
	def modifiers_steg(self) -> list:
		retList = []
		for mod in self.modifiers_list:
			retList.append(mod.replace(" ", ""))
		return retList

	@property
	def tournament_name(self):
		retStr = f"{self.name}"
		if self.speed != 100:
			retStr += f" ({self.speed}%)"
		if self.modifiers != ['NM']:
			retStr += f" [{self.modifiers_short}]"
		return retStr

	def __str__(self):
		return self.name

	@property
	def game_version(self):
		ret = self.brackets.first()
		if ret:
			return ret.tournament.config.version
		else:
			ret = self.qualifier.first()
		if ret:
			return ret.tournament.config.version
		else:
			return CH_VERSIONS[-1][0]

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		self.blake3 = self.blake3.upper() #Force these always upper
		self.icon = CHIcon.objects.get(name="ch_default_icon") if self.icon == None else self.icon
		self.md5 = self.md5.upper() #Steg is output as always upper
		if self.sngfile and self.sngfile.name.lower().endswith(".zip"):
			zip_file = SNGHandler(self.sngfile.open(mode='rb').read())
			self.sngfile.save(f"{zip_file.outputChartName}.sng",File(io.BytesIO(zip_file.build_sng())))
		super().save()

class BYOSChart(Chart):
	groups = models.ManyToManyField("Group", related_name="byos_setlist", verbose_name="Groups", blank=True, help_text="Groups using this chart in their BYOS Pool")
	brackets = None
	category = None

	class Meta:
		verbose_name = "BYOS Chart"
		verbose_name_plural = "BYOS Charts"
