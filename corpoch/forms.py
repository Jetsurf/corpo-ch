import pydantic
from django import forms
from .models import TournamentPlayer, Match
from .types import PlayerConfig, CH_Name
from .tasks import update_gsheet
from django.utils.safestring import mark_safe

class TournamentPlayerForm(forms.ModelForm):
    primary_ch_name_selection = forms.ChoiceField(
        widget=forms.RadioSelect,
        required=False,
        label="Clone Hero Names"
    )
    new_ch_name = forms.CharField(
        required=False,
        label="Add New Clone Hero Name",
        help_text="Type a name here and save to add it to this player's list.",
        strip=False,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off'
        })
    )
    delete_ch_name = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'delete_target_id'}),
        required=False,
        strip=False
    )

    class Meta:
        model = TournamentPlayer
        fields = '__all__'
        widgets = {
            'config': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_primary_name = None
        if self.instance and self.instance.pk:
            self._old_primary_name = self.instance.ch_name
        self.fields['primary_ch_name_selection'].help_text = mark_safe('''
            <style>
                #id_primary_ch_name_selection label {
                    display: flex !important; 
                    align-items: center;
                    margin-bottom: 4px;
                    width: 300px; /* Set a fixed width for the label to create a gap between the name and the button */
                }
                .ch-name-text {
                    width: 300px; /* Adjust this to make the gap wider or narrower */
                    margin-left: 8px;
                    white-space: pre-wrap;
                }
            </style>
        ''')

        if self.instance and self.instance.pk and self.instance.config:
            config_data = self.instance.config

            try:
                if isinstance(config_data, dict):
                    player_config = PlayerConfig(**config_data)
                else:
                    player_config = config_data

                choices = []
                for ch_item in player_config.names_list:
                    safe_name = ch_item.ch_name.replace("'", "\\'")

                    label_html = f'''
                        <span class="ch-name-text">{ch_item.ch_name}</span>
                        <button type="button"" 
                            onclick="document.getElementById('delete_target_id').value='{safe_name}'; document.querySelector('input[name=\\'_continue\\']').click();" 
                            style="border: none; background: none; cursor: pointer; padding: 0; font-size: 1.1em;" 
                            title="Delete {ch_item.ch_name}">
                            🗑️
                        </button>
                    '''

                    label = mark_safe(label_html)
                    choices.append((ch_item.ch_name, label))

                    if ch_item.is_primary:
                        self.initial['primary_ch_name_selection'] = ch_item.ch_name

                self.fields['primary_ch_name_selection'].choices = choices

            except pydantic.ValidationError:
                self.fields['primary_ch_name_selection'].choices = []

    def clean(self):
        cleaned_data = super().clean()
        selected_primary = cleaned_data.get('primary_ch_name_selection')
        new_name = cleaned_data.get('new_ch_name')
        target_to_delete = cleaned_data.get('delete_ch_name')

        raw_config_data = cleaned_data.get('config')

        try:
            if not raw_config_data:
                player_config = PlayerConfig(names_list=[])
            elif isinstance(raw_config_data, dict):
                player_config = PlayerConfig(**raw_config_data)
            else:
                player_config = raw_config_data
        except pydantic.ValidationError as e:
            raise forms.ValidationError(f"Stored configuration data is invalid: {e}")

        names_list = player_config.names_list

        if target_to_delete:
            names_list = [item for item in names_list if item.ch_name != target_to_delete]
            if selected_primary == target_to_delete:
                selected_primary = None

        if new_name:
            already_exists = any(item.ch_name == new_name for item in names_list)
            if not already_exists:
                is_first_item = len(names_list) == 0
                new_ch_name = CH_Name(ch_name=new_name, is_primary=is_first_item)
                names_list.append(new_ch_name)


        if selected_primary:
            for item in names_list:
                item.is_primary = (item.ch_name == selected_primary)

        if names_list and not any(item.is_primary for item in names_list):
            names_list[0].is_primary = True

        if names_list:
            for item in names_list:
                if item.is_primary:
                    self.instance.ch_name = item.ch_name
                    cleaned_data['ch_name'] = item.ch_name
                    break
        else:
            self.instance.ch_name = "</Null>"
            cleaned_data['ch_name'] = "</Null>"

        player_config.names_list = names_list
        cleaned_data['config'] = player_config 
        cleaned_data['delete_ch_name'] = ""

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()

        new_primary_name = instance.ch_name

        if self._old_primary_name is not None and self._old_primary_name != new_primary_name:

            submissions = instance.qualifiers.all()

            for sub in submissions:
                update_gsheet.delay(sub.id)

            player_matches = Match.objects.filter(players__player=instance).distinct()

            for match in player_matches:
                update_gsheet.delay(match.id)

        return instance