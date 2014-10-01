#!/usr/bin/env python

import re
from getpass import getpass
import requests
from collections import defaultdict

from gmusicapi import Mobileclient
from termcolor import colored
from lxml import html
import unidecode
from jaro import jaro_winkler_metric as jaro_winkler

PANDORA_LOGIN_URL = "https://www.pandora.com/login.vm"
PANDORA_LIKES_URL = "http://www.pandora.com/content/tracklikes"
PANDORA_STATIONS_URL = "http://www.pandora.com/content/stations"

class LoginException(Exception):
    pass

class PandoraClient(object):
    def __init__(self, email, password):
        self.session = requests.session()

        response = self.session.post(PANDORA_LOGIN_URL, data={
            "login_username": email,
            "login_password": password,
        })

        if "0;url=http://www.pandora.com/people/" not in response.text:
            raise LoginException("Pandora login failed, check email and password")

    def liked_tracks(self):
        """ Scrape likes from the Pandora web interface """

        like_start_index = 0
        thumb_start_index = 0

        tracks = defaultdict(list)
        more_pages = True

        while more_pages:
            response = self.session.get(PANDORA_LIKES_URL, params={
                "likeStartIndex": like_start_index,
                "thumbStartIndex": thumb_start_index,
            })

            tree = html.fromstring(response.text)

            for element in tree.find_class("infobox-body"):
                title = unicode(element.find("h3").text_content())
                title = title.strip()

                artist = unicode(element.find("p").text_content())
                artist = artist.strip()
                artist = re.sub(r"^by\s+", "", artist)

                station_elements = element.find_class("like_context_stationname")

                if station_elements:
                    station_name = unicode(station_elements[0].text_content())
                    station_name = station_name.strip()
                else:
                    # Bookmarked track
                    station_name = None

                tracks[station_name].append((artist, title))

            more_elements = tree.find_class("show_more")

            # There are more pages
            if more_elements:
                like_start_index = more_elements[0].get("data-nextlikestartindex")
                thumb_start_index = more_elements[0].get("data-nextthumbstartindex")
            else:
                more_pages = False

        return tracks

def normalise_metadata(value):
    """ Normalise a piece of song metadata for searching """

    # ASCII representation
    value = unidecode.unidecode(value)
    value = unicode(value)

    # Lowercase
    value = value.lower()

    # Remove secondary artists
    value = value.split(",")[0]
    value = re.sub(r"\([^\)]+\)|\[[^\]]+\]", "", value)
    value = re.sub(r"\bf(ea)?t\.?\b.+", "", value)

    # Remove extraneous whitespace
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip()

    return value

def fuzzy_artist_match(artist_a, artist_b):
    """ Check if the two artists are probably the same """

    return jaro_winkler(artist_a, artist_b) >= 0.7

def print_section_heading(heading):
    """ Print an underlined heading """

    print
    print u"%s\n%s" % (heading, "=" * len(heading))

def print_song(artist, title, indicator, colour):
    """ Print a song """

    print colored(
        u"[{indicator}] {artist} - {title}".format(
            indicator=indicator,
            artist=artist,
            title=title
        ),
        colour
    )

def print_gmusic_songs(songs, indicator, colour):
    """ Print Google Music song objects """

    for song in songs:
        artist = song["track"]["artist"]
        title = song["track"]["title"]
        print_song(artist, title, indicator, colour)

def search_gmusic(gmusic_client, artist, title):
    """ Search Google Music for a song, returns the best match """

    def _search_strings(artist, title):
        """ Increasingly generic search strings """

        yield artist + " " + title

        # Search again with the title normalised too
        title = normalise_metadata(title)
        yield artist + " " + title

    artist = normalise_metadata(artist)

    # No match
    status = 0
    best_match = None

    for search_string in _search_strings(artist, title):
        results = gmusic_client.search_all_access(search_string)["song_hits"]

        if results:
            result = results[0]

            gmusic_artist = normalise_metadata(result["track"]["artist"])

            # To stop spam songs being added to the playlist check that
            # the artists are roughly the same
            if fuzzy_artist_match(gmusic_artist, artist):
                # Good match
                status = 2
                best_match = result
                break
            elif status == 0:
                # Spam
                status = 1
                best_match = result

    return status, best_match

def match_pandora_with_gmusic(pandora_likes, gmusic_client):
    """ Match Pandora likes with Google Music """

    pandora_playlists = defaultdict(list)

    for station_name, songs in pandora_likes.items():
        if station_name:
            print_section_heading('Matching "%s"' % station_name)
        else:
            print_section_heading('Matching Bookmarks')

        for song in songs:
            artist, title = song

            status, match = search_gmusic(gmusic_client, artist, title)

            if status == 2:
                # Station playlist
                if station_name:
                    playlist_name = "Pandora - " + station_name
                    pandora_playlists[playlist_name].append(match)

                pandora_playlists["Pandora"].append(match)

                indicator, colour = "Y", "green"
            elif status == 1:
                indicator, colour = "S", "magenta"
            else:
                indicator, colour = "N", "red"

            print_song(artist, title, indicator, colour)

    return pandora_playlists

def sync_gmusic_playlists(client, playlists):
    """ Sync the specified playlists with the playlists on Google Music """

    gmusic_playlists = client.get_all_user_playlist_contents()
    gmusic_playlist_map = {playlist["name"]: playlist for playlist in gmusic_playlists}

    songs_added = 0
    songs_removed = 0

    # Update Google Music playlists
    for playlist_name, songs in playlists.items():
        print_section_heading('Syncing "%s"' % playlist_name)

        song_map = {song["track"]["nid"]: song for song in songs}

        # Get the playlist if it already exists
        gmusic_playlist = gmusic_playlist_map.get(playlist_name)

        # Playlist doesn't exist so create it
        if gmusic_playlist is None:
            new_playlist = True

            gmusic_playlist_id = client.create_playlist(playlist_name)

            song_ids_to_add = set(song["track"]["nid"] for song in songs)
            song_ids_to_remove = set()
        # Playlist exists so update it
        else:
            new_playlist = False

            gmusic_playlist_id = gmusic_playlist["id"]

            # Find song ids to add and remove from the playlist
            gmusic_song_map = {song["trackId"]: song for song in gmusic_playlist["tracks"]}
            gmusic_song_ids = set(gmusic_song_map.keys())
            new_song_ids = set(song_map.keys())
            song_ids_to_add = new_song_ids - gmusic_song_ids
            song_ids_to_remove = gmusic_song_ids - new_song_ids

        if new_playlist:
            print colored("New playlist", "blue")
        else:
            # Check if the playlist needs to be updated
            if len(song_ids_to_add) > 0 or len(song_ids_to_remove) > 0:
                print colored("Updating playlist", "blue")
            else:
                print colored("Up to date", "blue")
                continue

        # Check if there are songs that need to be added
        if song_ids_to_add:
            # Add songs to the Google Music playlist
            client.add_songs_to_playlist(gmusic_playlist_id, list(song_ids_to_add))
            songs_added += len(song_ids_to_add)

            songs_to_add = [song_map[x] for x in song_ids_to_add]
            print_gmusic_songs(songs_to_add, "+", "green")

        # Check if there are songs that need to be removed
        if song_ids_to_remove:
            # Remove songs from the Google Music playlist
            songs_to_remove = [gmusic_song_map[x] for x in song_ids_to_remove]
            entries_to_remove = [song["id"] for song in songs_to_remove]
            client.remove_entries_from_playlist(entries_to_remove)
            songs_removed += len(song_ids_to_remove)

            print_gmusic_songs(songs_to_remove, "-", "red")

    return songs_added, songs_removed

def pandora_to_google_music(pandora_email, pandora_password, gmusic_email, gmusic_password):
    """ Sync Pandora likes with Google Music playlists """

    gmusic_client = Mobileclient()
    gmusic_client.login(gmusic_email, gmusic_password)

    pandora_client = PandoraClient(pandora_email, pandora_password)

    pandora_likes = pandora_client.liked_tracks()
    pandora_like_count = sum(len(x) for x in pandora_likes.values())

    playlists = match_pandora_with_gmusic(pandora_likes, gmusic_client)
    gmusic_match_count = len(playlists.get("Pandora", []))

    songs_added, songs_removed = sync_gmusic_playlists(gmusic_client, playlists)

    print_section_heading("Summary")
    print "%d/%d songs matched" % (gmusic_match_count, pandora_like_count)
    print "{added}/{removed} changes to playlists".format(
        added=colored("+%d" % songs_added, "green"),
        removed=colored("-%d" % songs_removed, "red"),
    )

    return pandora_like_count, gmusic_match_count, songs_added, songs_removed

def main():
    """ Run pandora_to_google_music """

    pandora_email = raw_input("Pandora email: ")
    pandora_password = getpass("Pandora password: ")
    gmusic_email = raw_input("Google Music email [%s]: " % pandora_email)
    gmusic_password = getpass("Google Music password: ")

    if gmusic_email == "":
        gmusic_email = pandora_email

    pandora_to_google_music(
        pandora_email,
        pandora_password,
        gmusic_email,
        gmusic_password
    )

if __name__ == "__main__":
    main()
