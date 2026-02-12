import glob, codecs
import mutagen
from mutagen.id3 import ID3
from mutagen import MutagenError
import train_model
import spacy
from spacy_fastlang import LanguageDetector

root_dir = '/mnt/media/music-beets/'
data_file_full = 'data/lyrics_data_full.csv'
data_file = 'data/lyrics_data.csv'

badwords=['nigga', 'fuck', 'shit', 'bitch']
goodwords=['nokoshite', 'shitai', 'kesshite', 'shite', 'kaskushiteta', 'yurushite', 'sarakedashite', 'afuredashite']

nlp = spacy.load('en_core_web_sm')
nlp.add_pipe('language_detector')


with codecs.open(data_file_full, 'w', encoding='utf-8') as output:
    output.write('is_offensive,text\r\n')
count=0
for location in glob.iglob(root_dir + '**/*.flac', recursive=True):
    count += 1
    with codecs.open(data_file_full, 'a', encoding='utf-8') as output:
        lyrics = ''
        #print(location)
        try:
            file = mutagen.File(location)

            if location.endswith('.mp3'):
                if 'audio/mp3' in file.mime:
                    audio = ID3(location)
                    lyrics_tag = audio.getall('USLT')
                    lyrics = lyrics_tag.text
            if location.endswith('.flac'):
                file = mutagen.File(location)
                if 'audio/flac' in file.mime:
                    for tag in file.tags:
                        if tag[0] == 'LYRICS':
                            lyrics = tag[1]
                            break
        except MutagenError as e:
            print(f'file not found: {location}')
        lyrics = lyrics.replace('Tekst piosenki:\n', '')
        lyrics = lyrics.replace('Tekst piosenki:', '')
        lyrics = lyrics.replace('Historia edycji tekstu\n', '')
        lyrics = lyrics.replace('Historia edycji tekstu', '')
        doc = nlp(lyrics.replace('\n', ' '))

        if doc._.language == 'en':

            lyrics = lyrics.replace("\"", "\"\"\"\"")
            lyrics = lyrics.split('\n')
            for line in lyrics:
                if len(line) > 0:

                    if any(badword in line.lower() for badword in badwords):
                        score = 1
                        if any(goodword in line.lower() for goodword in goodwords):
                            score = 0
                    else:
                        score = 0
                    output.write(f'{score},\"{line}\"\r\n')
        else:
            print(doc._.language, location)

#dedup csv

lines_seen = set() # holds lines already seen
outfile = open(data_file, "w")
for line in open(data_file_full, "r"):
    if line not in lines_seen: # not a duplicate
        outfile.write(line)
        lines_seen.add(line)
outfile.close()

train_model.train()