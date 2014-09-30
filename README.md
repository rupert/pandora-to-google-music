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

1. You will be asked for your Pandora and Google Music credentials
1. The script will then scrape your liked songs from Pandora
1. It will then search for these songs in Google Music
1. Songs that match are added to Google Music playlists
1. Enjoy!
