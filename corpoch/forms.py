import pydantic
from django import forms
from .models import TournamentPlayer
from .types import TournamentPlayerConfig
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
        #widgets = {
        #    'config': forms.HiddenInput(),
        #}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

            if isinstance(config_data, list):
                try:
                    pydantic_configs = [TournamentPlayerConfig(**item) for item in config_data]
                    choices = []

                    for config in pydantic_configs:
                        safe_name = config.ch_name.replace("'", "\\'")

                        label_html = f'''
                            <span class="ch-name-text">{config.ch_name}</span>
                            <button type="submit" name="_continue" 
                                onclick="document.getElementById('delete_target_id').value='{safe_name}';" 
                                style="border: none; background: none; cursor: pointer; padding: 0; font-size: 1.1em;" 
                                title="Delete {config.ch_name}">
                                🗑️
                            </button>
                        '''

                        label = mark_safe(label_html)
                        choices.append((config.ch_name, label))

                    self.fields['primary_ch_name_selection'].choices = choices

                    for config in pydantic_configs:
                        if config.is_primary:
                            self.initial['primary_ch_name_selection'] = config.ch_name
                            break

                except pydantic.ValidationError as e:
                    self.fields['primary_ch_name_selection'].choices = []
            else:
                self.fields['primary_ch_name_selection'].choices = []

    def clean(self):
        cleaned_data = super().clean()
        selected_primary = cleaned_data.get('primary_ch_name_selection')
        new_name = cleaned_data.get('new_ch_name')
        target_to_delete = cleaned_data.get('delete_ch_name')

        raw_config_data = cleaned_data.get('config')
        if not isinstance(raw_config_data, list):
            raw_config_data = []

        try:
            pydantic_configs = [TournamentPlayerConfig(**item) for item in raw_config_data]
        except pydantic.ValidationError as e:
            raise pydantic.ValidationError(f"Stored configuration data is invalid: {e}")

        if target_to_delete:
            pydantic_configs = [config for config in pydantic_configs if config.ch_name != target_to_delete]
            if selected_primary == target_to_delete:
                selected_primary = None

        if new_name:
            already_exists = any(config.ch_name == new_name for config in pydantic_configs)
            if not already_exists:
                is_first_item = len(pydantic_configs) == 0
                new_config = TournamentPlayerConfig(ch_name=new_name, is_primary=is_first_item)
                pydantic_configs.append(new_config)

        if selected_primary:
            for config in pydantic_configs:
                config.is_primary = (config.ch_name == selected_primary)

        if pydantic_configs and not any(c.is_primary for c in pydantic_configs):
            pydantic_configs[0].is_primary = True

        if pydantic_configs:
            for config in pydantic_configs:
                if config.is_primary:
                    self.instance.ch_name = config.ch_name
                    cleaned_data['ch_name'] = config.ch_name
                    break
        else:
            self.instance.ch_name = "</Null>"
            cleaned_data['ch_name'] = "</Null>"

        cleaned_data['config'] = [config.model_dump() for config in pydantic_configs]
        cleaned_data['delete_ch_name'] = ""

        return cleaned_data