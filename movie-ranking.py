import shutil, os, asyncio, math
from pprint import pprint
from plexapi.server import PlexServer
from tqdm import tqdm
from functools import cmp_to_key
from datetime import datetime
from aiopyarr.models.host_configuration import PyArrHostConfiguration
from aiopyarr.radarr_client import RadarrClient

config = {}
with open("conf/plex-playlists.conf") as config_file:
    for line in config_file:
        name, var = line.partition("=")[::2]
        config[name.strip()] = var.strip()

IP = "192.168.1.191"
TOKEN = config['radarr_token']

async def get_movie_id(title, year):
    host_configuration = PyArrHostConfiguration(ipaddress=IP, api_token=TOKEN)
    async with RadarrClient(host_configuration=host_configuration) as client:
        movies = await client.async_get_movies()
        for movie in movies:
            if title == movie.title:
                print(f"{movie.title}: id={movie.id}, year = {movie.year}")

                if (year == movie.year or year == movie.year-1 or year == movie.year+1):
                    return movie.id

 
async def get_tags(id):
    host_configuration = PyArrHostConfiguration(ipaddress=IP, api_token=TOKEN)
    async with RadarrClient(host_configuration=host_configuration) as client:
        try:
            val = await client.async_get_tags_details(id)
            return val
        except:
            return None



async def delete_movie(id):
    host_configuration = PyArrHostConfiguration(ipaddress=IP, api_token=TOKEN)
    async with RadarrClient(host_configuration=host_configuration) as client:
        try:
            val = await client.async_delete_movies(id, delete_files=True, add_exclusion=True)
            return val
        except:
            return None


def get_my_rating(movie):
    if movie.rating is None:
        my_rating = movie.audienceRating*2    
        rating_str = f"{movie.audienceRating}+{movie.audienceRating}"
    else:
        my_rating = movie.audienceRating + movie.rating
        rating_str = f"{movie.rating}+{movie.audienceRating}"
    movie.reload()
    current_year = datetime.now().year
    year_adjust = max((10 - ((current_year - movie.year)*2)), 0) 
    my_rating += year_adjust
    rating_str += f"+{year_adjust}y"



    genres  = [genre.tag for genre in movie.genres]
    if 'Science Fiction' in genres or 'Fantasy' in genres:
        my_rating+=6
        rating_str += f"+6g"

    if 'Romance' in genres and ('Science Fiction' not in genres and 'Fantasy' not in genres):
        my_rating-=2
        rating_str += f"-2g"

    collections  = [collection.tag for collection in movie.collections]
    for str in ['IMDb Lowest Rated', 'Trakt Popular', 'Trakt Trending', 'Trakt Collected', 'Trakt Watched', 'TMDb Popular']:
        if str in collections:
            collections.remove(str)
    if len(collections) > 0:
        my_rating+=max(len(collections)*2, 6)
        rating_str += f"+{max(len(collections)*2, 6)}c"

    return my_rating, rating_str


def movie_compare(a, b):
    if get_my_rating(a) > get_my_rating(b):
        return 1
    return -1

def convert_size(size_bytes):
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

def get_folder_size(path):
    size = 0
    
    for path, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(path, f)
            size += os.path.getsize(fp)

    return convert_size(size)


path = '/mnt/media/video/movies'
total_size = shutil.disk_usage(path) 

movies_size = get_folder_size('/mnt/media/video/movies')
tv_size = get_folder_size('/mnt/media/video/tv')
print("Total free : " + str(convert_size(total_size.free)))
print("Movies size: " + str(movies_size))
print("TV size    : " + str(tv_size))


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
    print("Finding deletable movies")
    for movie in tqdm(movies.search(sort='rating,audienceRating', 
                               filters={'movie.audienceRating<<': 8, 'movie.label!=':['Keep']})):
        if movie.rating is None or movie.rating < 8:
            rating, rating_str = get_my_rating(movie)
            movies_list.append([rating, movie])
    #movies_list = sorted(movies_list, key = cmp_items_py3)
    print("Sorting movies")
    movies_list = sorted(movies_list, key=lambda x: x[0])
    print("Printing rankings")
    #for movie in [tuple[1] for tuple in movies_list[:10]+movies_list[-10:]]:
    for movie in [tuple[1] for tuple in movies_list[:100]]:
        genres  = [genre.tag for genre in movie.genres]
        collections  = [collection.tag for collection in movie.collections]
        rating, rating_str = get_my_rating(movie)
        # print(f"MyRating: {rating:.1f}, {rating_str} Rating: {movie.rating}, \
        #       Audience Rating: {movie.audienceRating}, Content Rating: {movie.contentRating}, \
        #       ViewCount: {movie.viewCount}, User Rating: {movie.userRating}, \
        #       Collections: {collections}, Genres: {genres} Title: {movie.title}, {movie.year}")


    for movie in [tuple[1] for tuple in movies_list[:10]]:
        genres  = [genre.tag for genre in movie.genres]
        collections  = [collection.tag for collection in movie.collections]
        rating, rating_str = get_my_rating(movie)
        print(f"MyRating: {rating:.1f}, {rating_str} Rating: {movie.rating}, \
              Audience Rating: {movie.audienceRating}, Content Rating: {movie.contentRating}, \
              ViewCount: {movie.viewCount}, User Rating: {movie.userRating}, \
              Collections: {collections}, Genres: {genres} Title: {movie.title}, {movie.year}")

        delete = input("Delete?")
        if delete == "y":
            id = asyncio.get_event_loop().run_until_complete(get_movie_id(movie.title, movie.year))
            val = asyncio.get_event_loop().run_until_complete(delete_movie(id))
        else:
            movie.addLabel("Keep")