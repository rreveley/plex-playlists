#let's find the thing we want to delete most
#if disk space is over 90% then
#iterate through TV shows in reverse order of age
#display shows with missing seasons.

from pathlib import Path
import os


rootdir = Path('/volume1/media/video/tv/')

files = Path(rootdir).glob("*/")

paths = sorted(Path(rootdir).iterdir(), key=os.path.getmtime, reverse=True)

for p in paths:
    print(p)
    if p.is_dir():
        seasons = sorted(Path(p).iterdir(), key=os.path.getmtime, reverse=True)
        for season in seasons:
            print(season)