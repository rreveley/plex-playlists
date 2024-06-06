import plexapi.utils
import string, math, os
from pprint import pprint
import requests
from tenacity import wait_exponential, retry, stop_after_attempt
from plexapi.server import PlexServer
import mutagen
from mutagen.id3 import ID3, COMM, POPM
from mutagen import MutagenError
from tqdm import tqdm
from functools import cmp_to_key

def get_my_rating(movie):
    my_rating = 0
    if movie.userRating is not None and movie.userRating >= 8:
        my_rating+=movie.userRating
    my_rating = my_rating*10 + min(movie.viewCount, 10)
    my_rating = my_rating*10 + movie.rating
    if len(movie.collections) > 0:
        my_rating+=2
    genres  = [genre.tag for genre in movie.genres]
    if 'Science Fiction' in genres or 'Fantasy' in genres:
        my_rating+=2
    if 'Romance' in genres:
        my_rating-=2
    my_rating = my_rating*10 + movie.audienceRating
    return my_rating

def movie_compare(a, b):
    if get_my_rating(a) > get_my_rating(b):
        return 1
    return -1

config = {}
with open("conf/plex-playlists.conf") as config_file:
    for line in config_file:
        name, var = line.partition("=")[::2]
        config[name.strip()] = var.strip()
        
cmp_items_py3 = cmp_to_key(movie_compare)

token = config['plex_token']
baseurl = 'http://192.168.1.147:32400'

if __name__ == '__main__':
    plex = PlexServer(baseurl, token, timeout=200)
    movies = plex.library.section('Movies')
    movies_list = []
    for movie in movies.search(sort='rating,audienceRating', 
                               filters={'movie.rating>>': 0, 'movie.rating<<': 8, 'movie.audienceRating<<': 8, 'movie.year<<': 2020}):
        rating = get_my_rating(movie)
        movies_list.append([rating, movie])
    #movies_list = sorted(movies_list, key = cmp_items_py3)
    movies_list = sorted(movies_list, key=lambda x: x[0])
    for movie in [tuple[1] for tuple in movies_list[:10]]:
        genres  = [genre.tag for genre in movie.genres]
        collections  = [collection.tag for collection in movie.collections]

        print(f"MyRating: {get_my_rating(movie)}, Rating: {movie.rating}, \
              Audience Rating: {movie.audienceRating}, Content Rating: {movie.contentRating}, \
              ViewCount: {movie.viewCount}, User Rating: {movie.userRating}, \
              Collections: {collections}, Genres: {genres} Title: {movie.title}, {movie.year}")

        #for location in movie.locations:
            #print(location)
            #os.remove(location)