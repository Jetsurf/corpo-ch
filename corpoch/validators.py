def validate_chart_file(file):
    import io
    from zipfile import ZipFile
    from django.core.exceptions import ValidationError

    file.seek(0)
    filename = file.name.lower()
    if not (filename.endswith(".sng") or filename.endswith(".zip")):
        raise ValidationError('Unsupported file extension. Must be .zip or .sng')
    if filename.endswith(".sng"):
        header = file.read(6)
        if header != b"SNGPKG":
            raise ValidationError('Invalid .sng')
    if filename.endswith(".zip"):
        header = file.read(4)
        file.seek(0)
        if header != b"\x50\x4B\x03\x04":
            raise ValidationError('Invalid .zip')
        else:
            with ZipFile(io.BytesIO(file.read()), 'r') as zip_file:
                all_files = zip_file.namelist()

                containing_paths = []
                for file_path in all_files:
                    if file_path.endswith('song.ini'):
                        if file_path == 'song.ini':
                            dir_path = ""
                        else:
                            dir_path = file_path.rsplit('/',1)[0]
                        containing_paths.append(dir_path)

                if not containing_paths:
                    raise ValidationError('Zip contains no song.ini')

                target_dir = min(containing_paths,key=len)
                if target_dir == "":
                    filtered_files = [f for f in all_files if "/" not in f and f != ""]
                    file_paths = [f for f in all_files if "/" not in f and f != ""]
                else:
                    filtered_files = [f.lower().split('/')[-1] for f in all_files if f.startswith(target_dir + "/") and "/" not in f.split(target_dir+"/")[1] and f.split('/')[-1] != "" ]
                    file_paths = [f for f in all_files if f.startswith(target_dir + "/") and "/" not in f.split(target_dir+"/")[1] and f.split('/')[-1] != "" ]

                music_names = ("guitar.","bass.","rhythm.","vocals.","vocals_1.","vocals_2.","drums.","drums_1.","drums_2.","drums_3.","drums_4.","keys.","song.")
                music_exts = ("mp3","ogg","opus","wav")
                valid_notes = ["notes.chart","notes.mid"]
                valid_ini = "song.ini"

                count_ini = filtered_files.count(valid_ini)
                count_notes = sum(1 for f in filtered_files if f in valid_notes)

                has_ini = count_ini == 1
                has_notes = count_notes == 1
                has_music = any(f.startswith(music_names) and f.split('.')[-1] in music_exts for f in filtered_files)

                if has_ini and has_notes and has_music:
                    pass
                else:
                    if not has_ini: raise ValidationError(f'Zip contains invalid number of song.ini files: {count_ini}')
                    if not has_notes: raise ValidationError(f'Zip contains invalid number of valid notes files: {count_notes}')
                    if not has_music: raise ValidationError('Zip contains no valid music files')
