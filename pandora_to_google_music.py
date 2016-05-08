#!/usr/bin/env python

import re
from getpass import getpass
from collections import defaultdict
import difflib

import requests
from gmusicapi import Mobileclient
from termcolor import colored
from lxml import html
import unidecode

class LoginException(Exception):
    pass

class PandoraClient(object):
    LOGIN_URL = "https://www.pandora.com/login.vm"
    LIKES_URL = "http://www.pandora.com/content/tracklikes"
    STATIONS_URL = "http://www.pandora.com/content/stations"

    def __init__(self, email, password):
        self.session = requests.session()

        response = self.session.post(PandoraClient.LOGIN_URL, data={
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
        page = 1

        while more_pages:
            response = self.session.get(PandoraClient.LIKES_URL, params={
                "likeStartIndex": like_start_index,
                "thumbStartIndex": thumb_start_index,
            })

            print_section_heading('Fetching Pandora Likes (page %d)' % page)

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

                print_song(artist, title)

            more_elements = tree.find_class("show_more")

            # There are more pages
            if more_elements:
                like_start_index = more_elements[0].get("data-nextlikestartindex")
                thumb_start_index = more_elements[0].get("data-nextthumbstartindex")
            else:
                more_pages = False

            page += 1

        return tracks

    def stations(self):
        """ Scrape station names from the Pandora web interface """

        response = self.session.get(PandoraClient.STATIONS_URL)
        tree = html.fromstring(response.text)

        stations = []

        for element in tree.findall(".//h3"):
            station_name = unicode(element.text_content().strip())
            stations.append(station_name)

        return stations

def normalise_metadata1(value):
    """ Normalise a piece of song metadata for searching """

    # ASCII representation
    value = unidecode.unidecode(value)
    value = unicode(value)

    # Lowercase
    value = value.lower()

    # Remove secondary artists (after comma or "ft.")
    value = re.split(r",|\bf(ea)?t\.?\b", value, 2)[0].strip()

    # Remove anything in brackets
    value = re.sub(r"\([^\)]+\)|\[[^\]]+\]", "", value)

    # Remove extraneous whitespace
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip()

    return value

def normalise_metadata2(value):
    """
    More aggressive metadata normalisation

    Assumes value has been normalised using normalise_metadata1 already.
    """

    # Remove "the" from the start
    value = value.lstrip("the").lstrip(" ")

    # Remove anything after "and" or "&"
    value = re.split(r"\s(and|&)\s", value, 2)[0].strip()

    return value

def metadata_normaliser(*args):
    """ Increasingly normalised values for searching/comparison """

    values = args
    yield values

    values = [normalise_metadata1(x) for x in values]
    yield values

    values = [normalise_metadata2(x) for x in values]
    yield values

def is_spam_artist(artist_a, artist_b):
    """ Check if an artist match is spam/cover """

    for a, b in metadata_normaliser(artist_a, artist_b):
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.6:
            return False

    return True

def print_section_heading(heading):
    """ Print an underlined heading """

    print
    print u"%s\n%s" % (heading, "=" * len(heading))

def print_song(artist, title, indicator="", colour=None):
    """ Print a song """

    if indicator:
        indicator = "[%s] " % indicator

    print colored(
        u"{indicator}{artist} - {title}".format(
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

    # No match
    status = 0
    best_match = None

    for search_artist, search_title in metadata_normaliser(artist, title):
        search_string = search_artist + " " + search_title
        results = gmusic_client.search_all_access(search_string)["song_hits"]

        for result in results:
            gmusic_artist = result["track"]["artist"]

            # To stop spam songs being added to the playlist check that
            # the artists are roughly the same
            if not is_spam_artist(gmusic_artist, artist):
                # Good match
                status = 2
                best_match = result
                break
            elif status == 0:
                # Spam
                status = 1
                best_match = result

        # Good match found
        if status == 2:
            break

    return status, best_match

def match_songs_with_gmusic(gmusic_client, songs):
    """ Match songs with Google Music """

    matched_songs = []

    for song in songs:
        artist, title = song

        status, match = search_gmusic(gmusic_client, artist, title)

        if status == 2:
            matched_songs.append(match)
            indicator, colour = "Y", "green"
        elif status == 1:
            indicator, colour = "S", "magenta"
        else:
            indicator, colour = "N", "red"

        print_song(artist, title, indicator, colour)

    return matched_songs

def match_playlists_with_gmusic(gmusic_client, playlists):
    """ Match playlists with Google Music """

    matched_playlists = dict()

    for playlist_name, songs in playlists.items():
        print_section_heading('Matching "%s" (%d songs)' % (playlist_name, len(songs)))
        matched_songs = match_songs_with_gmusic(gmusic_client, songs)
        matched_playlists[playlist_name] = matched_songs

    return matched_playlists

def sync_gmusic_playlists(client, playlists):
    """ Sync the specified playlists with the playlists on Google Music """

    gmusic_playlists = client.get_all_user_playlist_contents()
    gmusic_playlist_map = {playlist["name"]: playlist for playlist in gmusic_playlists}

    songs_added = 0
    songs_removed = 0

    # Update Google Music playlists
    for playlist_name, songs in playlists.items():
        song_map = {song["track"]["nid"]: song for song in songs}
        song_ids = set(song_map.keys())

        print_section_heading('Syncing "%s" (%d songs)' % (playlist_name, len(song_ids)))

        # Get the playlist if it already exists
        gmusic_playlist = gmusic_playlist_map.get(playlist_name)

        # Playlist doesn't exist so create it
        if gmusic_playlist is None:
            new_playlist = True

            gmusic_playlist_id = client.create_playlist(playlist_name)

            song_ids_to_add = song_ids
            song_ids_to_remove = set()
        # Playlist exists so update it
        else:
            new_playlist = False

            gmusic_playlist_id = gmusic_playlist["id"]

            # Find song ids to add and remove from the playlist
            gmusic_song_map = {song["trackId"]: song for song in gmusic_playlist["tracks"]}
            gmusic_song_ids = set(gmusic_song_map.keys())
            song_ids_to_add = song_ids - gmusic_song_ids
            song_ids_to_remove = gmusic_song_ids - song_ids

        if new_playlist:
            print "New playlist"
        else:
            # Check if the playlist needs to be updated
            if len(song_ids_to_add) > 0 or len(song_ids_to_remove) > 0:
                print "Updating playlist"
            else:
                print "Up to date"
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

    # Get liked Pandora tracks
    pandora_likes = pandora_client.liked_tracks()
    pandora_like_count = sum(len(x) for x in pandora_likes.values())

    # Get Pandora stations
    pandora_stations = set(pandora_client.stations())

    pandora_playlists = defaultdict(list)

    # Copy all songs to main playlist
    # Add Pandora prefix to playlist names
    # Remove deleted stations (songs will be in main playlist)
    for station_name, songs in pandora_likes.items():
        # Copy songs to main playlist
        pandora_playlists["Pandora"].extend(songs)

        # Check station hasn't been deleted
        if station_name in pandora_stations:
            pandora_playlists["Pandora - %s" % station_name] = songs

    # Match Pandora likes with Google Music
    playlists = match_playlists_with_gmusic(gmusic_client, pandora_playlists)
    gmusic_match_count = len(playlists.get("Pandora", []))

    # Sync Google Music playlists
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
