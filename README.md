A python script to sync liked songs in Pandora to Google Play Music All Access playlists.

After running the script you will have a "Pandora" playlist with all of the songs you have liked.
There will also be playlists for each station that has liked songs.
The format for these is "Pandora - STATION NAME".

## Dependencies

```bash
# lxml dependencies
yum install libxml2-devel libxslt-devel

virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python pandora_to_google_music.py
```
As the script I will:

1. Ask for your Pandora and Google Music login details
1. Scrape your likes from Pandora
1. Match these songs with Google Music
1. Add the songs that match to Google playlists

Enjoy!
