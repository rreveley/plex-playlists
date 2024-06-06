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
    async with LidarrClient(host_configuration=host_configuration) as client:
        data = await client.async_search(related_artist)
        artist = data[0].artist
        if artist.added is None or artist.added > datetime.datetime(1,1,1,0,1):
            print(f"\t\t{artist.artistName} already added")
            return False
        artist.lastAlbum=None
        artist.nextAlbum=None
        artist.qualityProfileId = 1
        artist.metadataProfileId = 6
        artist.monitored = False
        artist.path = f'/music/{related_artist}'
        await client.async_add_artist(artist)
        print(f"\t{related_artist} added")
        return True


import spotipy
from plexapi.server import PlexServer

from spotipy.oauth2 import SpotifyClientCredentials
token = config['plex_token']
baseurl = 'http://192.168.1.147:32400'

plex = PlexServer(baseurl, token, timeout=200)
music = plex.library.section('Music-beets')
best_artists = music.search(libtype='artist', sort='userRating:desc')



sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=config['spotify_id'],
                                                            client_secret=config['spotify_secret']))
count = 0
for artist in best_artists:
    result = sp.search(q=f'artist:{artist.title}', type='artist')
    artist = result['artists']['items'][0]
    for item in result['artists']['items']:
        if item['popularity'] > artist['popularity']:
            artist = item

    print(f"Located {artist['name']} on Spotify")
    artist_id = artist['id']
    related_artists = sp.artist_related_artists(artist_id)

    print(f"Checking {artist['name']}")
    for related_artist in related_artists['artists']:
        val = asyncio.get_event_loop().run_until_complete(async_example(related_artist['name']))
        if val:
            break
    if not val:
        continue
    count=count+1
    if count > 5:
        break