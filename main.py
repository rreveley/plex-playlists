import plexapi.utils
from tenacity import wait_exponential, retry, stop_after_attempt
from plexapi.server import PlexServer
import mutagen
from mutagen.id3 import ID3, COMM, POPM
from mutagen import MutagenError
from tqdm import tqdm

import numpy as np
import profanity_check

badwords=['nigga', 'fuck', 'shit', 'bitch']


token = 'ZfxxHwnW2pyd6egLfzPi'
baseurl = 'http://192.168.1.147:32400'


def is_explicit(track):
    location = munge_location(track.locations[0])
    lyrics = ''
    try:
        file = mutagen.File(location)

        if location.endswith('.mp3'):
            if 'audio/mp3' in file.mime:
                audio = ID3(location)
                lyrics_tag = audio.getall('USLT')
                if isinstance(lyrics_tag, list):
                    if len(lyrics_tag) > 0:
                        lyrics = lyrics_tag[0].text
                else:
                    lyrics = lyrics_tag.text
        if location.endswith('.flac'):
            file = mutagen.File(location)
            if 'audio/flac' in file.mime:
                for tag in file.tags:
                    if tag[0] == 'LYRICS':
                        lyrics = tag[1]
                        break

        if len(lyrics) == 0:
            return -1, []
        lines = lyrics.split('\n')
        val = profanity_check.predict(lines)
        result = np.where(val == 1)
        bad_lines = []
        if 1 in val:
            for index in result[0]:
                bad_lines.append(lines[index])
            return 1, bad_lines
            # for word in profanity.CENSOR_WORDSET:
            #     if str(word) in lyrics:
            #         index = lyrics.index(str(word))
            #         start = max(index-10, 0)
            #         end = min(index+10, len(lyrics))
            #         return True, (str(word)+' : '+lyrics[start:end].replace('\n', ' '))

        return 0, []
    except MutagenError as e:
        print(f'file not found: {location}')
        return 0, []

@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def rate_albums():
    print('Rating albums')
    results = music.search(libtype='album', filters={'track.userRating>>': 0})
    for album in results:
        track_results = music.search(libtype='track', filters={'album.id': album.ratingKey, 'track.userRating>>': 0})
        total = 0
        count = 0
        for track in track_results:
            if track.userRating is not None and is_music(track):
                total += track.userRating
                count += 1
        if count > 0:
            average = round(total / count, 1)
            if album.userRating != average:
                print("Album Rating:", album.parentTitle, album.title, album.userRating, '->', average)
                album.rate(average)

@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def rate_artists():
    print('Rating artists')
    results = music.search(libtype='artist', filters={'track.userRating>>': 0})

    for artist in results:
        track_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating>>': 0})
        total = 0
        count = 0
        for track in track_results:
            if track.userRating is not None and is_music(track):
                total += track.userRating
                count += 1
        if count > 0:
            average = round(total / count, 1)
            if artist.userRating != average:
                print("Artist Rating:", artist.title, artist.userRating, '->', average)
                artist.rate(average)

def contains_track(list, track):
    count = 0
    for item in list:
        if item.title == track:
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

def daily_listen(clean=False):

    # 5* songs 100 least play count
    # 4* songs 50 least play count
    # 3* songs 50 least play count
    # 5* artists 30 unrated songs
    # 4* artists 30 unrated songs
    # Released ion last year 100 songs

    # for p in music.playlists():
    #     print(p)
    #     if 'Daily Listen' in p.title:
    #         p.delete()

    tracks = []
    limit = len(tracks)+50
    results = music.search(libtype='track', filters={'track.userRating': 10}, sort='viewCount:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(len(tracks), '5*', track.grandparentTitle, track, track.viewCount)
            tracks.append(track)
            if len(tracks) >= limit:
                break


    results = music.search(libtype='track', filters={'track.userRating': 8}, sort='viewCount:asc')
    limit = len(tracks)+25
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(len(tracks), '4*',track.grandparentTitle,  track, track.viewCount)
            tracks.append(track)
            if len(tracks) >= limit:
                break

    results = music.search(libtype='track', filters={'track.userRating': 6}, sort='viewCount:asc')
    limit = len(tracks)+10
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(len(tracks), '3*',track.grandparentTitle, track, track.viewCount)
            tracks.append(track)
            if len(tracks) >= limit:
                break

    limit = len(tracks)+5
    results = music.search(libtype='track', filters={'artist.userRating>>': 8}, sort='viewCount:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(len(tracks), '5* Artist', track.grandparentTitle, track, track.viewCount)
            tracks.append(track)
            if len(tracks) >= limit:
                break

    limit = len(tracks)+5
    results = music.search(libtype='track', filters={'artist.userRating>>=': 6, 'artist.userRating<<': 8}, sort='viewCount:asc')
    for track in results:
        if is_music(track) and (not clean or is_clean(track)) and contains_artist(tracks, track.grandparentTitle) == 0 and contains_track(tracks, track.title) == 0:
            print(len(tracks), '4* Artist', track.grandparentTitle, track, track.viewCount)
            tracks.append(track)
            if len(tracks) >= limit:
                break

    if clean:
        adjust_playlist(music, 'Daily Listen (Clean)', tracks)
    else:
        adjust_playlist(music, 'Daily Listen', tracks)


def one_track_unrated_artist():
    #playlist with one track from each unrated artist
    tracklist = []
    results = music.search(libtype='artist')
    for artist in results:
        if artist.userRating is None:
            tracks = music.search(libtype='track',filters={'artist.id': artist.ratingKey}, limit=10)
            #tracks = artist.tracks()
            for track in tracks:
                if is_music(track):
                    tracklist.append(track)
                    print(len(tracklist), 'Unrated Artists', track.grandparentTitle, track, track.viewCount)
                    break

    adjust_playlist(music, 'Unrated Artists', tracklist)

@retry(wait=wait_exponential(multiplier=2, min=2, max=30),  stop=stop_after_attempt(5))
def adjust_playlist(library, title, tracklist):
    print(f"Updating {title} with {len(tracklist)} tracks")
    exists = False
    for playlist in library.playlists():
        if playlist.title == title:
            exists = True
            break

    for track in tracklist:
        if exists:
            if track not in playlist.items():
                playlist.addItems(items=[track])
        if not exists:
            playlist = library.createPlaylist(title, items=[track])
            exists = True

    #select all items with that mood
    tracks = library.search(libtype='track', filters={'track.mood': title}, container_size=1000)
    for track in tracks:
        if track not in tracklist:
            existing_moods = [mood.tag for mood in track.moods]
            if title in existing_moods:
                data = plexapi.utils.tag_helper("mood", [title], remove=True)
                track.edit(**data)
                track.reload()

    for track in playlist.items():
        existing_moods = [mood.tag for mood in track.moods]
        if track not in tracklist:
            playlist.removeItems([track])
        if title not in existing_moods:
            data = plexapi.utils.tag_helper("mood", existing_moods + [title])
            track.edit(**data)
            track.reload()


def is_clean(track):
    library = plex.library.section('Music-beets')
    for playlist in library.playlists():
        if playlist.title == 'Explicit Tracks':
            exists = True
            break

    if track not in playlist.items():
        return True
    return False


def is_music(track):
    for mood in track.moods:
        if mood.tag == 'Non-Music':
            return False
    return track.duration is not None and track.duration > 60*1000

#50 of the best songs I've never rated
@retry(wait=wait_exponential(multiplier=2, min=2, max=60),  stop=stop_after_attempt(10))
def best_unrated(clean=False):
    results = music.search(libtype='artist', sort='userRating:desc,viewCount:desc')
    #find 10 best artists
    best_artists = []
    for artist in results:
        if len(best_artists) < 20:
            if artist.title != 'Various Artists':
                unrated_tracks_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating': -1})
                print('Best Artist:', artist.title, 'Rating', artist.userRating, 'Views', artist.viewCount, 'Unrated Tracks', len(unrated_tracks_results))
                for track in unrated_tracks_results:
                    if is_music(track) and (not clean or is_clean(track)):
                        best_artists.append(artist)
                        break


    print(best_artists)

    #now need 4 best songs from the 10 best artists
    list = []
    for artist in best_artists:
        print(artist.title, artist.userRating, artist.viewCount)

        #first get tracks from least heard rated albums,that way we rotate the albums day to day
        unrated_tracks_results = music.search(libtype='track', filters={'artist.id': artist.ratingKey, 'track.userRating': -1}, sort='album.viewCount:asc')
        limit = len(list) + 4
        for track in unrated_tracks_results:
            if is_music(track) and (not clean or is_clean(track)) and contains_track(list, track.title) == 0 and contains_album(list, track.parentTitle) < 2:
                list.append(track)
                print('\t', track.parentTitle, track.title)
            if len(list) >= limit:
                break

    #Find least heard similar artist, add one unheard track
    for artist in best_artists:
        similar_artists = []
        for similar in artist.similar:
            similar_artist_results = music.search(libtype='artist', filters={'artist.title==': similar.tag})
            for similar_artist in similar_artist_results:
                similar_artists.append((similar_artist.viewCount, similar_artist))
        similar_artists = sorted(similar_artists, key=lambda tup: tup[0])
        limit = len(list) + 1
        for similar_artist in similar_artists:
            similar_tracks_results = music.search(libtype='track',filters={'artist.id': similar_artist[1].ratingKey, 'track.userRating': -1})
            for track in similar_tracks_results:
                if is_music(track)  and (not clean or is_clean(track))and contains_artist(list, track.grandparentTitle) == 0 and contains_track(list, track.title) == 0:
                    print(artist.title, '->', track.grandparentTitle, '-', track.title)
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
    return location


def read_tags():
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


def check_lyrics():
    music = plex.library.section('Music-beets')
    explicit = []
    clean = []
    unknown = []
    pbar = tqdm(music.search(libtype='track'))
    for track in pbar:
        if is_music(track):
            result, bad_lines = is_explicit(track)
            if result == 1:
                for line in bad_lines:
                    if any(badword in line.lower() for badword in badwords):
                        pass
                    else:
                        pbar.set_postfix({f'{track.grandparentTitle} {track.title}': f'{line}'})
                explicit.append(track)
            elif result == 0:
                clean.append(track)
            else:
                unknown.append(track)
    adjust_playlist(music, 'Explicit Tracks', explicit)
    #adjust_playlist(music, 'Clean Tracks', clean)
    adjust_playlist(music, 'No Lyrics Tracks', unknown)

def clear_moods(library, title):
    tracks = library.search(libtype='track', filters={'track.mood': title})
    for track in tracks:
        existing_moods = [mood.tag for mood in track.moods]
        if title in existing_moods:
            data = plexapi.utils.tag_helper("mood", [title], remove=True)
            track.edit(**data)
            track.reload()


if __name__ == '__main__':
    plex = PlexServer(baseurl, token, timeout=200)
    music = plex.library.section('Music-beets')

    #clear_moods(plex.library.section('Music-beets'), 'Selected Unrated')
    #clear_moods(plex.library.section('Music-beets'), 'Selected Unrated (Clean)')

    #clear_moods(plex.library.section('Music'), 'Selected Unrated')
    #clear_moods(plex.library.section('Music'), 'Selected Unrated (Clean)')


    rate_albums()
    rate_artists()
    best_unrated()

    daily_listen()
    daily_listen(clean=True)

    write_tags()
    read_tags()


    one_track_unrated_artist()
    check_lyrics()
