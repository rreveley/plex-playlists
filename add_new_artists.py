"""Example usage of aiopyarr."""
import asyncio, datetime
from aiopyarr.models.host_configuration import PyArrHostConfiguration
from aiopyarr.lidarr_client import LidarrClient
from aiopyarr.models.lidarr import (
    LidarrAlbum,
    LidarrAlbumEditor,
    LidarrAlbumHistory,
    LidarrAlbumStudio,
    LidarrArtist,
    LidarrCommands,
    LidarrEventType,
    LidarrImportList,
    LidarrImportListActionType,
    LidarrImportListMonitorType,
    LidarrImportListType,
    LidarrManualImport,
    LidarrMetadataProfile,
    LidarrMetadataProvider,
    LidarrRelease,
    LidarrSortKeys,
    LidarrTrackFile,
    LidarrTrackFileEditor,
    LidarrWantedCutoff,
)
config = {}
with open("conf/plex-playlists.conf") as config_file:
    for line in config_file:
        name, var = line.partition("=")[::2]
        config[name.strip()] = var.strip()
        
IP = "192.168.1.191"
TOKEN = config['lidarr_token']


async def async_example(related_artist):
    """Example usage of aiopyarr."""
    host_configuration = PyArrHostConfiguration(ipaddress=IP, api_token=TOKEN)
    async with LidarrClient(host_configuration=host_configuration, request_timeout=300) as client:
        data = await client.async_search(related_artist)
        artist = data[0].artist
        if artist.added is None or artist.added > datetime.datetime(1,1,1,0,1):
            print(f"\t\t{artist.artistName} already added")
            return False
        artist.lastAlbum=None
        artist.nextAlbum=None
        artist.qualityProfileId = 1
        artist.metadataProfileId = 3
        artist.monitored = False
        artist.path = f'/music/{related_artist}'
        try:
            await client.async_add_artist(artist)
        except:
            print(f"Exception adding {related_artist}")
        print(f"\t{related_artist} added")
        return True

async def add_album(artist, album):
    host_configuration = PyArrHostConfiguration(ipaddress=IP, api_token=TOKEN)
    async with LidarrClient(host_configuration=host_configuration) as client:
        data = await client.async_search(artist)
        artist = data[0].artist
        if artist.added is None or artist.added > datetime.datetime(1,1,1,0,1):
            print(f"\t\t{artist.artistName} already added")
            if artist.monitored == False or 5 not in artist.tags:
                artist.monitored = True
                artist.tags.append(5)
                data = await client.async_edit_artists(artist)
        else:
            print(f"{artist.artistName} needed")



import pylast, os
from plexapi.server import PlexServer


#do 1001 list
#with open('1001albums.tsv') as file:
#    for line in file:
#        artist = line.split("\t")[0].strip()
#        album = line.split("\t")[1].strip()
#        asyncio.get_event_loop().run_until_complete(add_album(artist, album))



last_api_key = config['last_api_key']
last_api_secret = config['last_api_secret']

SESSION_KEY_FILE = os.path.join(os.path.expanduser("~"), ".session_key")
network = pylast.LastFMNetwork(last_api_key, last_api_secret)
if not os.path.exists(SESSION_KEY_FILE):
    skg = pylast.SessionKeyGenerator(network)
    url = skg.get_web_auth_url()

    print(f"Please authorize this script to access your account: {url}\n")
    import time
    import webbrowser

    #webbrowser.open(url)

    while True:
        try:
            session_key = skg.get_web_auth_session_key(url)
            with open(SESSION_KEY_FILE, "w") as f:
                f.write(session_key)
            break
        except pylast.WSError:
            time.sleep(1)
else:
    session_key = open(SESSION_KEY_FILE).read()

network.session_key = session_key

#get all frequently played last.fm artists
user = network.get_user("rreveley")


top_artists = user.get_top_artists(limit=200)
for artist in top_artists:
    if int(artist[1]) > 100:
        print("Checking top artists:", artist[0].name, artist[1])
        val = asyncio.get_event_loop().run_until_complete(async_example(artist[0].name))


token = config['plex_token']
baseurl = 'http://192.168.1.147:32400'

plex = PlexServer(baseurl, token, timeout=200)
music = plex.library.section('Music-beets')
best_artists = music.search(libtype='artist', sort='userRating:desc')


count = 0
for artist in best_artists:
    pyartist = pylast.Artist(artist.title, network)
    similar_artists = pyartist.get_similar(limit=5)


    print(f"Checking {artist.title}")
    for similar_artist in similar_artists:
        similar_artist_name = similar_artist[0].name
        val = asyncio.get_event_loop().run_until_complete(async_example(similar_artist_name))
        if val:
            break
    if not val:
        continue
    count=count+1
    if count > 5:
        break