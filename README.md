A python script to sync liked songs in Pandora to Google Play Music All Access playlists.

After running the script you will have a "Pandora" playlist with all of the songs you have liked.
There will also be a playlist for each station that has liked songs.
The format for these is "Pandora - STATION NAME".

## Install

```bash
# lxml dependencies
yum install libxml2-devel libxslt-devel

virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
./pandora-to-google-music
```

1. You will be asked for your Pandora and Google Music credentials
1. The script will then scrape your liked songs from Pandora
1. These songs are then searched for in Google Music
1. Songs that match are added to Google Music playlists
1. Enjoy!
