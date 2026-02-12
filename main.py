import plexapi.utils
from pprint import pprint
from tenacity import wait_exponential, retry, stop_after_attempt
from plexapi.server import PlexServer
import mutagen
from mutagen.id3 import ID3, COMM, POPM
from mutagen import MutagenError
from tqdm import tqdm
import spotipy, math, re, requests, string, random, time
import numpy as np
from difflib import SequenceMatcher
from spotipy.oauth2 import SpotifyClientCredentials
import pathlib

from beets.dbcore.query import SubstringQuery, AndQuery
from beets.library import Library


badwords=[]
with open("conf/nsfw.txt") as config_file:
    for line in config_file:
        badwords.append(line.strip().lower())


config = {}
with open("conf/plex-playlists.conf") as config_file:
    for line in config_file:
        name, var = line.partition("=")[::2]
        config[name.strip()] = var.strip()

token = config['plex_token']
baseurl = 'http://192.168.1.147:32400'

def is_clean(track):
    if 'Explicit' in [mood.tag for mood in track.moods]:
        return False
    if 'No Lyrics' in [mood.tag for mood in track.moods]:
        return False
    if 'Explicit-Manual' in [mood.tag for mood in track.moods]:
        return False
    if  'Clean' in [mood.tag for mood in track.moods]:
        return True
    if  'Instrumental' in [mood.tag for mood in track.moods]:
        return True

    return False

#0 is clean, 1 is explicit, -1 is unknown, 2 is instrumental
def is_explicit_beets(track):
    lib_music = Library("/mnt/docker/beets/beets.db")

    query_response = lib_music.items(
        AndQuery([
            SubstringQuery('path', munge_location(track.locations[0])),
        ])
    )
    if len(query_response) == 0:
        print(f'Track not found in beets.db {track.locations[0]}')
        return -1
    unknown = True
    for item in query_response:
        lyrics = item.get('lyrics')
        # Check for instrumental
        if lyrics and '[Instrumental]' in lyrics and len(lyrics) < 50:
            return 2
        if any(substring in lyrics for substring in badwords):
            bad_lines = []
            lines = lyrics.split('\n')
            for line in lines:
                for badword in badwords:
                    if badword in line.lower():
                        bad_lines.append(line)
                        break
            if bad_lines:
                print(f'Explicit lyrics found in {track.grandparentTitle} - {track.title}:')
                #for bad_line in bad_lines:
                #    print(f'  {bad_line}')
            return 1
        if item.get('lyrics') != 'empty' and item.get('lyrics') != '':
            unknown = False

    if unknown:
        return -1
    else:  # lyrics exist but they aren't is_explicit
        val = is_censored_explicit(lyrics)
        if val == 1:
            return 1
        return 0

def is_censored_explicit(lyrics):
    if not lyrics or lyrics == 'empty':
        return 0

    censored_patterns = ['f-', 'n-', 'b-', 's-', 'sh-']
    
    lyrics_lower = lyrics.lower()
    lines = lyrics.split('\n')
    lines_lower = [line.lower() for line in lines]
    
    found_patterns = False
    for pattern in censored_patterns:
        for i, line_lower in enumerate(lines_lower):
            index = 0
            while True:
                index = line_lower.find(pattern, index)
                if index == -1:
                    break
                # Check if pattern is not immediately followed by a letter or hyphen
                next_char_index = index + len(pattern)
                if next_char_index >= len(line_lower) or (not line_lower[next_char_index].isalpha() and line_lower[next_char_index] != '-'):
                    if not found_patterns:
                        print(f'Censored explicit content found:')
                        found_patterns = True
                    print(f'  {lines[i]}')
                    break
                index += 1
    
    return 1 if found_patterns else 0


def is_explicit_quick(track):
    if "[Explicit]" in track.locations[0]:
        return 1
    else:
        return 0

#@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def rate_albums():
    log_prefix="rate_albums"

    print('Rating albums')
    results = music.search(libtype='album', filters={'track.userRating>>': 0})
    for album in tqdm(results):
        track_results = music.search(libtype='track', filters={'album.guid': album.guid, 'track.userRating>>': 0})
        total = 0
        count = 0
        for track in track_results:
            if track.userRating is not None and is_music(track):
                total += track.userRating
                count += 1
        if count > 0:
            average = round(total / count, 1)
            if album.userRating != average:
                tqdm.write(f"{log_prefix}: {album.guid} {album.ratingKey} {album.parentTitle} {album.title} {album.userRating} -> {average}")
                album.rate(average)

@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def rate_artists():
    print('Rating artists')
    results = music.search(libtype='artist', filters={'track.userRating>>': 0})

    for artist in tqdm(results):
        track_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating>>': 0}, sort='userRating:asc')
        total = 0
        count = 0
        exp_avg = 4
        titles = []
        for track in track_results:
            if track.userRating is not None and is_music(track) and track.title not in titles:
                titles.append(track.title)
                total += track.userRating
                count += 1
                exp_avg = exp_avg*0.9+track.userRating*0.1 
        if count > 0:
            exp_avg = round(exp_avg, 1)
            average = round(total / count, 1)
            if artist.userRating != exp_avg:
                tqdm.write(f"Artist Rating: {artist.title} {artist.userRating} -> {exp_avg}")
                artist.rate(exp_avg)
#TODO: Handle when two sets of ()
def strip_remixes(title):
    open = title.find("(")
    close = title.find(")", open)
    if open > -1 and close > -1:
        remix = -1
        for val in ["remix", "mix", "edit", "a deal with god", "version"]:
            remix = max(title.lower().find(val), remix)
        if open < remix < close:
            title = re.sub(r"[\(\[].*?[\)\]]", "", title).strip()

    return title

def contains_track(list, track):
    count = 0
    for item in list:
        stripped_item = strip_remixes(item.title)
        stripped_track = strip_remixes(track)
        if SequenceMatcher(None, stripped_item, stripped_track).ratio() > 0.8:
            count += 1
    return count

def contains_album(list, album):
    count = 0
    for track in list:
        if track.parentTitle == album:
            count += 1
    return count

def contains_artist(list, artist):
    count = 0
    for track in list:
        if track.grandparentTitle == artist:
            count += 1
    return count

def contains_genre(list, genre_to_count):
    count = 0
    for track in list:
        genres  = [genre.tag for genre in track.genres]
        if genre_to_count in genres:
            count += 1
    return count

def daily_listen(clean=False):

    # 5* songs 50 least play count
    # 4* songs 25 least play count
    # 3* songs 10 least play count
    # 5* artists 5 unrated songs
    # 4* artists 5 unrated songs
    # Released ion last year 100 songs

    # for p in music.playlists():
    #     print(p)
    #     if 'Daily Listen' in p.title:
    #         p.delete()
    if clean:
        log_prefix = 'daily_clean'
    else:
        log_prefix = 'daily'
    log_mid='na'
    print(f'{log_prefix}-{log_mid} Creating Daily Listen')
    log_mid='least-heard-5star'
    tracks = []
    limit = len(tracks)+50
    results = music.search(libtype='track', filters={'track.userRating': 10, 'artist.title!=': 'Various Artists'}, sort='lastViewedAt:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) \
            and contains_artist(tracks, track.grandparentTitle) == 0 \
            and contains_track(tracks, track.title) == 0        :
                print(f'{log_prefix}-{log_mid} Adding {track.grandparentTitle} - {track.title} - {track.viewCount}')
                tracks.append(track)
                if len(tracks) >= limit:
                    break

    log_mid='least-heard-4star'
    results = music.search(libtype='track', filters={'track.userRating': 8, 'artist.title!=': 'Various Artists'}, sort='lastViewedAt:asc')
    limit = len(tracks)+25
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(f'{log_prefix}-{log_mid} Adding {track.grandparentTitle} - {track.title} - {track.viewCount}')
            tracks.append(track)
            if len(tracks) >= limit:
                break

    log_mid='least-heard-3star'
    results = music.search(libtype='track', filters={'track.userRating': 6, 'artist.title!=': 'Various Artists'}, sort='lastViewedAt:asc')
    limit = len(tracks)+10
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(f'{log_prefix}-{log_mid} Adding {track.grandparentTitle} - {track.title} - {track.viewCount}')
            tracks.append(track)
            if len(tracks) >= limit:
                break

    log_mid = "5star-artist-least-heard-track"
    limit = len(tracks)+5
    results = music.search(libtype='track', filters={'artist.userRating>>': 8, 'artist.title!=': 'Various Artists'}, sort='lastViewedAt:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(f'{log_prefix}-{log_mid} Adding {track.grandparentTitle} - {track.title} - {track.viewCount}')
            tracks.append(track)
            if len(tracks) >= limit:
                break
    log_mid = "4star-artist-least-heard-track"
    limit = len(tracks)+5
    results = music.search(libtype='track', filters={'artist.userRating>>=': 6, 'artist.userRating<<': 8, 'artist.title!=': 'Various Artists'}, sort='lastViewedAt:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(f'{log_prefix}-{log_mid} Adding {track.grandparentTitle} - {track.title} - {track.viewCount}')
            tracks.append(track)
            if len(tracks) >= limit:
                break

    if clean:
        adjust_playlist(music, 'Daily Listen (Clean)', tracks)
    else:
        adjust_playlist(music, 'Daily Listen', tracks)

def one_track_unrated_artist():
    log_prefix="unrated_artist"
    log_mid="na"

    #playlist with one track from each unrated artist
    tracklist = []
    results = music.search(libtype='artist')
    for artist in results:
        if artist.userRating is None:
            
            tracks = get_popular(artist)
            if len(tracks) > 0:
                for track in tracks:
                    if is_music(track):
                        tracklist.append(track)
                        print(f'{log_prefix}-popular \t Artist:{track.grandparentTitle} Album:{track.parentTitle} Track:{track.title}')
                        break
            else:
                tracks = music.search(libtype='track',filters={'artist.id': artist.ratingKey}, limit=10)
                #tracks = artist.tracks()
                for track in tracks:
                    if is_music(track):
                        tracklist.append(track)
                        print(f'{log_prefix}-any \t Artist:{track.grandparentTitle} Album:{track.parentTitle} Track:{track.title}')
                        break
    random.shuffle(tracklist)
    adjust_playlist(music, 'Unrated Artists', tracklist)

#retry(wait=wait_exponential(multiplier=2, min=2, max=30),  stop=stop_after_attempt(5))
def adjust_playlist(library, title, tracklist):
    print(f"Updating {title} with {len(tracklist)} tracks")
    exists = False
    print(f"Get contents of {title} playlist")
    for playlist in library.playlists():
        if playlist.title == title:
            exists = True
            break

    print(f"Add items to {title} playlist")
    for track in tracklist:
        if exists:
            if track not in playlist.items():
                playlist.addItems(items=[track])
        if not exists:
            playlist = library.createPlaylist(title, items=[track])
            exists = True

    #select all items with that mood
    tracks = library.search(libtype='track', filters={'track.mood': title})
    print(f"Remove existing moods from tracks not in tracklist")
    for track in tracks:
        if track not in tracklist:
            existing_moods = [mood.tag for mood in track.moods]
            if title in existing_moods:
                track.removeMood([title])

    print(f"Remove from playlist anything not in tracklist, add mood to everything in playlist")
    for track in playlist.items():
        existing_moods = [mood.tag for mood in track.moods]
        if track not in tracklist:
            playlist.removeItems([track])
        if title not in existing_moods:
                track.addMood([title])


def is_music(track):
    for mood in track.moods:
        if mood.tag == 'Non-Music':
            return False
    return track.duration is not None and track.duration > 60*1000 #60 seconds

#50 of the best songs I've never rated
#@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def best_unrated(clean=False):
    log_prefix="unrated"
    log_mid="na"
    print(f"{log_prefix}-{log_mid} Creating Selected Unrated")
    results = music.search(libtype='artist', sort='userRating:desc,lastViewedAt:desc')
    #find 10 best artists
    log_mid="best_artist"
    print(f"{log_prefix} Finding best artists")
    best_artists = []
    for artist in results:
        if len(best_artists) < 20:
            if artist.title != 'Various Artists':
                unrated_tracks_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating': -1})
                print(f'{log_prefix}-{log_mid} Checking Artist:', artist.title, 'Rating', artist.userRating, 'Unrated Tracks', len(unrated_tracks_results))
                for track in unrated_tracks_results:
                    if is_music(track) and (not clean or is_clean(track)):
                        best_artists.append(artist)
                        print(f'{log_prefix}-{log_mid} \t Adding Artist: {artist.title}')
                        break


    print(f"{log_prefix}-{log_mid} Selected artists: {best_artists}")
    log_mid="songs_of_best_artists"
    #now need 4 best songs from the 10 best artists
    list = []
    for artist in best_artists:
        print(f'{log_prefix}-{log_mid} {artist.title} {artist.userRating}')

        #first get tracks from least heard rated albums,that way we rotate the albums day to day
        unrated_tracks_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating': -1}, sort='album.lastViewedAt:asc')
        limit = len(list) + 4
        for track in unrated_tracks_results:
            if is_music(track) and (not clean or is_clean(track)) and contains_track(list, track.title) == 0 and contains_album(list, track.parentTitle) < 2:
                list.append(track)
                print(f'{log_prefix}-{log_mid} \t Album:{track.parentTitle} Track:{track.title}')
            if len(list) >= limit:
                break
            
    log_mid="similar_artists"
    #Find least heard similar artist, add one unheard track
    for artist in best_artists:
        similar_artists = []
        for similar in artist.similar:
            similar_str = similar.tag.translate(str.maketrans('','',string.punctuation))
            similar_artist_results = music.search(libtype='artist', filters={'artist.title==': similar_str})
            for similar_artist in similar_artist_results:
                print(f'{log_prefix}-{log_mid} Similar to:{artist.title} is {similar_artist.title} viewCount: {similar_artist.viewCount}')
                similar_artists.append((similar_artist.viewCount, similar_artist))
        similar_artists = sorted(similar_artists, key=lambda tup: tup[0])
        limit = len(list) + 1
        for similar_artist in similar_artists:
            print(f'{log_prefix}-{log_mid} \t Finding 1 unrated track by {similar_artist[1].title}')
            similar_tracks_results = music.search(libtype='track',filters={'artist.id': similar_artist[1].ratingKey, 'track.userRating': -1})
            for track in similar_tracks_results:
                if is_music(track)  and (not clean or is_clean(track))and contains_artist(list, track.grandparentTitle) == 0 and contains_track(list, track.title) == 0:
                    print(f'{log_prefix}-{log_mid} \t \t Adding {track.grandparentTitle} - {track.parentTitle} - {track.title}')
                    list.append(track)
                    if len(list) >= limit:
                        break
            if len(list) >= limit:
                break

    #random.shuffle(list)
    if clean:
        adjust_playlist(music, 'Selected Unrated (Clean)', list)
    else:
        adjust_playlist(music, 'Selected Unrated', list)


def write_tags():
    print("Writing ratings as comments to file")
    results = music.search(libtype='track', filters={'track.userRating>>': 0})
    for track in tqdm(results):
        if track.userRating > 8:
            stars = 255
            comment = u'ooooo'
        elif track.userRating > 6:
            stars = 192
            comment = u'oooo'
        elif track.userRating > 4:
            stars = 128
            comment = u'ooo'
        elif track.userRating > 2:
            stars = 64
            comment = u'oo'
        elif track.userRating > 0:
            stars = 1
            comment = u'oo'

        location = munge_location(track.locations[0])

        try:
            file = mutagen.File(location)
            if 'audio/flac' in file.mime:
                if 'RATING' in file.tags:
                    if file.tags['RATING'][0] != f'{track.userRating * 10:.0f}':
                        tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, UserRating:{track.userRating}")
                        file.tags['RATING'] = f'{track.userRating * 10:.0f}'
                        file.save()
                else:
                    tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, UserRating:{track.userRating}")
                    file.tags['RATING'] = f'{track.userRating * 10:.0f}'
                    file.save()
            if 'audio/mp3' in file.mime:
                audio = ID3(location)

                popm = audio.getall('POPM')
                comms = audio.getall('COMM::XXX')


                if len(popm) == 0 or popm[0].rating != stars:
                    tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, UserRating:{track.userRating}")

                    if len(popm) == 0:
                        tqdm.write('Unrated')
                        audio.add(POPM(encoding=3, rating=stars, email='rr@email.com'))
                    else:
                        tqdm.write(f'Old Rating {popm[0].rating}')
                        popm[0].rating=stars
                        audio.setall('POPM', popm)
                        audio.save()

                for comm in comms:
                    if comm == 'o' or comm == 'oo' or comm == 'ooo' or comm == 'oooo' or comm == 'ooooo':
                        if comm != comment:
                            tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, UserRating:{track.userRating}")

                            tqdm.write(f'Old Comment {comm.text}')
                            audio.add(COMM(encoding=3, text=comment))
                            audio.save()
                if len(comms) == 0:
                    tqdm.write('Uncommented')
                    audio.add(COMM(encoding=3, text=comment))
                    audio.save()
        except MutagenError:
            tqdm.write(f'File not found {location}')


def munge_location(location):
    #location = location.replace('/volume1/media/music-beets', 'Y:')
    #location = location.replace('/volume1/media/music', 'Z:')
    #location = location.replace('/', '\\ ')
    location = location.replace('/volume1/', '/mnt/')
    return location


def read_tags():
    print("Reading comments from file and updating to plex")
    # now do the opposite and go through every file and check if it has ratings, then apply to Plex
    artist_results = music.search(libtype='artist', sort='userRating:desc')
    for artist in tqdm(artist_results):
        results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating': -1})
        for track in results:
            location = munge_location(track.locations[0])

            try:
                if location.endswith('.mp3'):
                    file = mutagen.File(location)
                    if 'audio/mp3' in file.mime:
                        audio = ID3(location)
                        popm = audio.getall('POPM')
                        comms = audio.getall('COMM::XXX')
                        if len(popm) > 0:
                            if popm[0].rating == 255:
                                tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:10")
                                track.rate(10)
                            elif popm[0].rating >= 192:
                                tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:8")
                                track.rate(8)
                            elif popm[0].rating == 1:
                                tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:2")
                                track.rate(2)
                if location.endswith('.flac'):
                    file = mutagen.File(location)
                    if 'audio/flac' in file.mime:
                        for tag in file.tags:
                            if tag[0] == 'RATING':
                                if tag[1] == '100':
                                    tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:10")
                                    track.rate(10)
                                if tag[1] == '80':
                                    tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:8")
                                    track.rate(8)
                                if tag[1] == '20':
                                    tqdm.write(f"Artist:{track.grandparentTitle} Album:{track.parentTitle}, Track:{track.title}, NewUserRating:8")
                                    track.rate(2)

            except MutagenError:
                tqdm.write(f'File not found {location}')

def check_lyrics_one_off():
    log_prefix = 'lyrics'
    print('Checking lyrics')
    music = plex.library.section('Music-beets')
    explicit = []
    clean = []
    unknown = []

    title = "Naked Steel (The Warrior's Saga)"
    advancedFilters = {
    'and': [
        {'title=': f"{title}"},
    ]
    }

    pbar = tqdm(music.search(libtype='track', filters=advancedFilters))

    for track in pbar:
        if is_music(track):
            result = is_explicit_beets(track)
            existing_moods = [mood.tag for mood in track.moods]
            if result == 1:
                if 'Explicit' not in existing_moods:
                    track.addMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Explicit')
                if 'Clean' in existing_moods:
                    track.removeMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Clean')
                if 'No Lyrics' in existing_moods:
                    track.removeMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing No Lyrics')
                explicit.append(track)
            elif result == 0:
                if 'Explicit' in existing_moods:
                    track.removeMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Explicit')
                if 'Clean' not in existing_moods:
                    track.addMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Clean')
                if 'No Lyrics' in existing_moods:
                    track.removeMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing No Lyrics')
                clean.append(track)
            else:
                if 'Explicit' in existing_moods:
                    track.removeMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Explicit')
                if 'Clean' in existing_moods:
                    track.removeMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Clean')
                if 'No Lyrics' not in existing_moods:
                    track.addMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding No Lyrics')
                unknown.append(track)
    else:
        track.addMood(['Non-Music'])

def check_lyrics():
    log_prefix = 'lyrics'
    print('Checking lyrics')
    music = plex.library.section('Music-beets')

    print('Querying all tracks')


    advancedFilters = {
    'and': [
        {'mood!=': 'LyricsChecked2'},
    ] }

    # advancedFilters = {
    # 'and': [
    #     {'mood!=': 'Non-Music'},
    #     {'mood!=': 'Clean'},
    #     {'mood!=': 'Explicit'},
    #     {'mood!=': 'Instrumental'},
    #     {'mood!=': 'No Lyrics'},
    #     { 'or': [
    #     {'mood=': 'LyricsChecked1'},
    #     {'mood=': 'LyricsChecked2'},
    # ] }
    # ]
    # }
    pbar = tqdm(music.search(libtype='track', filters=advancedFilters, limit=5000))

    for track in pbar:
        if is_music(track):
            track.removeMood('LyricsChecked1')
            track.addMood('LyricsChecked2')
            result = is_explicit_beets(track)
            existing_moods = [mood.tag for mood in track.moods if mood.tag in {"Explicit", "Clean", "No Lyrics", "Instrumental"}]
            if result == 1:
                if 'Explicit' not in existing_moods:
                    track.addMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Explicit')
                if 'Clean' in existing_moods:
                    track.removeMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Clean')
                if 'Instrumental' in existing_moods:
                    track.removeMood(['Instrumental'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Instrumental')
                if 'No Lyrics' in existing_moods:
                    track.removeMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing No Lyrics')
            elif result == 0:
                if 'Explicit' in existing_moods:
                    track.removeMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Explicit')
                if 'Clean' not in existing_moods:
                    track.addMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Clean')
                if 'Instrumental' in existing_moods:
                    track.removeMood(['Instrumental'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Instrumental')
                if 'No Lyrics' in existing_moods:
                    track.removeMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing No Lyrics')
            elif result == 2:
                if 'Explicit' in existing_moods:
                    track.removeMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Explicit')
                if 'Clean' not in existing_moods:
                    track.addMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Clean')
                if 'Instrumental' not in existing_moods:
                    track.addMood(['Instrumental'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding Instrumental')
                if 'No Lyrics' in existing_moods:
                    track.removeMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing No Lyrics')

            else:
                if 'Explicit' in existing_moods:
                    track.removeMood(['Explicit'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Explicit')
                if 'Clean' in existing_moods:
                    track.removeMood(['Clean'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Clean')
                if 'Instrumental' in existing_moods:
                    track.removeMood(['Instrumental'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Removing Instrumental')
                if 'No Lyrics' not in existing_moods:
                    track.addMood(['No Lyrics'])
                    print(f'{log_prefix} Modifying: {track.grandparentTitle} - {track.parentTitle} - {track.title} {existing_moods} Adding No Lyrics')
    else:
        track.addMood(['Non-Music'])

def clear_moods(library, title):
    tracks = library.search(libtype='track', filters={'track.mood': title})
    for track in tracks:
        existing_moods = [mood.tag for mood in track.moods]
        if title in existing_moods:
            data = plexapi.utils.tag_helper("mood", [title], remove=True)
            track.edit(**data)
            track.reload()
@retry(wait=wait_exponential(multiplier=2, min=2, max=60), stop=stop_after_attempt(10))
def best_georgia(clean=False):
    if clean:
        log_prefix = 'georgia_clean'
    else:
        log_prefix = 'georgia'
    log_mid='na'
    list = []

    tracks = music.search(libtype='track', filters={'track.mood': 'Georgia Spotify'}, sort='track.lastViewedAt:asc')

    #TODO: Change this so it always gets 50 tracks
    log_mid = "spotify_matches"
    print(f'{log_prefix}-{log_mid} Specifically requested tracks')
    limit = len(list)+50
    for track in tracks:
        if is_music(track) and (not clean or is_clean(track)) and contains_track(list, track.title) == 0 and contains_album(list, track.parentTitle) < 1:
            print(f'{log_prefix}-{log_mid} \t {track.grandparentTitle} {track.title}')
            list.append(track)
            if len(list) >= limit:
                break

    #collect all artists from this list
    artists_str = set()
    for track in tracks:
        artists_str.add(track.grandparentTitle)

    artists = []
    log_mid="artists"
    for artist_str in artists_str:
        print(f'{log_prefix}-{log_mid} Spotify artist: {artist_str}')
        artist = music.search(libtype='artist', filters={'artist.title==': artist_str})

        artists.append(artist)
    log_mid="artists_popular"
    #least heard of most popular tracks by that artist
    print(f'{log_prefix}-{log_mid} Least Heard Popular Tracks by Known Artists')
    for artist_name in artists:
        limit = len(list) + 1
        for artist in artist_name:
            min_pop = None
            tracks = get_popular(artist)
            for track in tracks:
                if min_pop is None or track.lastViewedAt < min_pop.lastViewedAt:
                    min_pop = track
            print(f'{log_prefix}-{log_mid} Adding: {artist.title} - {track.title} views: {track.viewCount}')
            if min_pop is not None:
                list.append(min_pop)



    #least heard track of 4 or 5 rating by that artist
    log_mid="artists_high_rated"
    print(f'{log_prefix}-{log_mid} High Rated Tracks by Known Artists')
    for artist_name in artists:
        limit = len(list) + 4
        for artist in artist_name:
            results = music.search(libtype='track',filters={'artist.id': artist.ratingKey, 'track.userRating>>=': 8}, sort='track.lastViewedAt:asc')

            for track in results:
                if track is not None:
                    if is_music(track):
                        if (not clean or is_clean(track)):
                            if contains_track(list, track.title) == 0:
                                if contains_album(list, track.parentTitle) < 1:
                                    list.append(track)
                                    print(f'{log_prefix}-{log_mid} Adding: {artist.title} - {track.title} views: {track.viewCount}')
                                if len(list) >= limit:
                                    break

    #plus one track from a similar artist
    log_mid="similar_artists"
    print(f'{log_prefix}-{log_mid} Tracks by similar artists')
    for artist_name in artists:
        for artist in artist_name:
            similar_artists = []
            for similar in artist.similar:
                similar_str = similar.tag.translate(str.maketrans('','',string.punctuation))
                similar_artist_results = music.search(libtype='artist', filters={'artist.title==': similar_str})
                for similar_artist in similar_artist_results:
                    print(f'{log_prefix}-{log_mid} Similar to {artist.title} adding {similar_artist.title} views: {similar_artist.viewCount}')
                    similar_artists.append((similar_artist.viewCount, similar_artist))
            similar_artists = sorted(similar_artists, key=lambda tup: tup[0])
            limit = len(list) + 1
            for similar_artist in similar_artists:
                similar_tracks_results = music.search(libtype='track', filters={'artist.id': similar_artist[1].ratingKey, 'track.userRating>>=': 8}, sort='track.lastViewedAt:asc')
                for track in similar_tracks_results:
                    if is_music(track) and (not clean or is_clean(track)) and contains_artist(list, track.grandparentTitle) == 0 and contains_track(list, track.title) == 0:
                        print(f'{log_prefix}-{log_mid} \t Adding: {track.grandparentTitle} - {track.title} views: {track.viewCount}')
                        list.append(track)
                        if len(list) >= limit:
                            break
                if len(list) >= limit:
                    break

    clean_list = []
    for track in list:
        if is_clean(track):
            clean_list.append(track)


    # random.shuffle(list)
    if clean:
        adjust_playlist(music, 'Georgia List (Clean)', clean_list)
    else:
        adjust_playlist(music, 'Georgia List', list)


def fetch(path):
    url = baseurl

    header = {'Accept': 'application/json'}
    params = {'X-Plex-Token': token,
              'includePopularLeaves': '1'
              }

    r = requests.get(url + path, headers=header, params=params, verify=False)
    return r.json()['MediaContainer']['Metadata'][0]['PopularLeaves']['Metadata']

def get_popular(artist):
    ratingKey_lst = []
    track_lst = []

    try:
        ratingKey_lst += fetch('/library/metadata/{}'.format(artist.ratingKey))
        for tracks in ratingKey_lst:
            track_lst.append(plex.fetchItem(int(tracks['ratingKey'])))
    except KeyError as e:
        print('Artist: {} does not have any popular tracks listed.'.format(artist.title))
        print('Error: {}'.format(e))

    return track_lst

def clean_string(str):
    result = str
    result = result.replace('\'', '')
    result = result.replace('Hard-FI', 'Hard-Fi')
    result = result.replace('Party (feat. André 3000)', 'Party')
    result = result.replace('a‐ha', 'a-ha')
    return result

def tag_spotify_playlist():

    log_prefix = 'tag_spotify'
    log_mid = 'na'
    print(f'{log_prefix}-{log_mid} Tag Spotify')
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=config['spotify_id'],
                                                            client_secret=config['spotify_secret']))

    pl_id = 'spotify:playlist:5vLF2mLkE8Xei0NEWX9nO8'
    offset = 0
    tracks = []
    try:
        while True:
            response = sp.playlist_items(pl_id,
                                        offset=offset,
                                        fields='items.track.id,items.track.artists.name,items.track.album.name,items.track.name,items.track.popularity',
                                        additional_types=['track'])

            if len(response['items']) == 0:
                break

            #pprint(response['items'])
            offset = offset + len(response['items'])
            #print(offset, "/", response['total'])

            for item in response['items']:
                artist_str = clean_string(item['track']['artists'][0]['name'])
                album_str = clean_string(item['track']['album']['name'])
                track_str = clean_string(item['track']['name'])
                print(f'{log_prefix} Spotify Artist:{artist_str} Album:{album_str} Track:{track_str}')
                track = music.search(libtype='track', filters={'artist.title==': artist_str, 'album.title==': album_str, 'track.title==':track_str})
                #if len(track) == 0:
                #    track = music.search(libtype='track', filters={'artist.title==': artist_str, 'track.title': track_str})
                #if len(track) == 0:
                #    track = music.search(libtype='track', filters={'album.title==': album_str, 'track.title':track_str})
                if len(track) > 0:
                    print(f'{log_prefix} \t Found Artist:{track[0].grandparentTitle} Album:{track[0].parentTitle} Track:{track[0].title}')
                    tracks.append(track[0])
        adjust_playlist(music, 'Georgia Spotify', tracks)
    except:
        print(f"{log_prefix} tag spotify failed")

def tag_popularity():
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=config['spotify_id'],
                                                            client_secret=config['spotify_secret']))

    tracks = music.search(libtype='track', filters={'track.userRating>>=': 5, 'track.mood!=':['Pop:0', 'Pop:25', 'Pop:50', 'Pop:75', 'Pop:100']}, sort='track.userRating')
    for track in tracks:
        result = sp.search(q=f'artist:{track.grandparentTitle} track:{track.title}', type='track')
        if(len(result['tracks']['items'])>0):
            pop=result['tracks']['items'][0]['popularity']
            print(f"Searching {track.grandparentTitle} {track.title}, Finding: {result['tracks']['items'][0]['artists'][0]['name']} {result['tracks']['items'][0]['name']}, Setting Pop:{pop}")
            new_mood = f'Pop:{math.ceil(pop/25)*25}'
            existing_moods = [mood.tag for mood in track.moods]
            for existing_mood in existing_moods:
                if existing_mood.startswith("Pop:") and existing_mood != new_mood:
                    track.removeMood(existing_mood)
            if new_mood not in existing_moods:
                track.addMood([new_mood])

def popular_songs(clean=False):
    log_prefix = 'popular'
    log_mid = 'na'
    limit = 100
    tracklist = []
    tracks = music.search(libtype='track', filters={'track.userRating>>=': 5}, sort='track.ratingCount:desc', limit=1000)
    tracks = sorted(tracks, key=lambda track: track.viewCount, reverse=True)
    for track in tracks:
        if is_music(track) and (not clean or is_clean(track)) and contains_track(tracklist, track.title) == 0 and contains_album(tracklist, track.parentTitle) == 0  and contains_artist(tracklist, track.grandparentTitle) < 2:
            print(f'{log_prefix}-{log_mid} \t {track.grandparentTitle} {track.title} Popularity:{track.ratingCount} PlayCount:{track.viewCount}')
            tracklist.append(track)
            if len(tracklist) >= limit:
                break
    adjust_playlist(music, 'Popular Songs', tracklist)

def find_split_albums():
    log_prefix="merge_albums"

    print('Find Split Albums')
    results = music.search(libtype='album', sort='artist.titleSort:asc,titleSort:asc')
    oldTitle = ""
    for album in results:
        if album.parentTitle is None:
            continue
        title = clean_string(album.title)
        if title == oldTitle:
            #we found two albums with the same name, but what if there are more?
            if "," in title:
                albums = music.search(libtype='album', filters={'album.title': clean_string(album.title), 'artist.id': album.parentRatingKey})
            else:
                albums = music.search(libtype='album', filters={'album.title=': clean_string(album.title), 'artist.id': album.parentRatingKey})
            #check if they have the same path
            tracks = music.search(libtype='track', filters={'album.id': album.ratingKey})
            outer_path = "a"
            outer_name = "a"
            if len(tracks)> 0:
                outer_path = pathlib.Path(tracks[0].locations[0]).parent
                outer_name = pathlib.Path(tracks[0].locations[0]).name
            else:
                continue
            for inner_album in albums:
                if inner_album.ratingKey != album.ratingKey:
                    inner_path = "b"
                    inner_name = "b"
                    tracks = music.search(libtype='track', filters={'album.id': inner_album.ratingKey})
                    if len(tracks)> 0:
                        inner_path = pathlib.Path(tracks[0].locations[0]).parent
                        inner_name = pathlib.Path(tracks[0].locations[0]).name
                    else:
                        continue

                    if inner_path == outer_path and inner_name != outer_name:
                        print(f"Merging - {album.parentTitle} - {album.title}")
                        album.merge([inner_album.ratingKey])

        oldTitle = title

def find_merged_albums():
    log_prefix="unmerge_albums"

    print('Find Over Merged Albums')
    results = music.search(libtype='album', sort='artist.titleSort:asc,titleSort:asc')
    for album in tqdm(results):
        tracks = music.search(libtype='track', filters={'album.id': album.ratingKey})
        for track in tracks:
            for inner_track in tracks:
                if inner_track.title == track.title:
                    if track.index==inner_track.index and track.parentIndex == inner_track.parentIndex:
                        if track.ratingKey != inner_track.ratingKey:
                            print(f"{album.parentTitle} - {album.title}")
                            print()




if __name__ == '__main__':
    plex = PlexServer(baseurl, token, timeout=200)
    music = plex.library.section('Music-beets')
    #check_lyrics_one_off()
    check_lyrics()
    daily_listen(clean=True)

    popular_songs()
    best_unrated()
    daily_listen()
    daily_listen(clean=True)
    one_track_unrated_artist()

    #tag_spotify_playlist()
    #best_georgia(clean=False)
    #best_georgia(clean=True)
    find_split_albums()

    #get popularity of songs
    #tag_popularity()
    
    rate_albums()
    rate_artists()

    write_tags()
    read_tags()
    find_merged_albums()
    