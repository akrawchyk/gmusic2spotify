#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
import sqlite3
import threading

from fuzzywuzzy import fuzz
from gmusicapi import Mobileclient
import spotify


# services account info
google_music_email = ''
google_music_password = ''
spotify_username = ''
spotify_password = ''


def ask_for_google_music_api():
    """Make an instance of the Google Music api and attempt to login with it.
    Return the authenticated api.
    """

    # We're not going to upload anything, so the Mobileclient is what we want.
    api = Mobileclient()
    logged_in = False
    attempts = 0

    while not logged_in and attempts < 3:
        logged_in = api.login(google_music_email, google_music_password)
        attempts += 1

    if not api.is_authenticated():
        print "Sorry, those Google Music credentials weren't accepted."
        sys.exit()

    return api


def ask_for_db_connection():
    """Make an instance of sqlite in memory and connect to it and return that
    connection.
    """
    conn = sqlite3.connect(':memory:')
    conn.text_factory = str
    return conn


def ask_for_spotify_session():
    """Make an instance of a Spotify session. Uses a separate thread for
    processing user login based on pyspotify's documentation
    """
    logged_in_event = threading.Event()

    def connection_state_listener(session):
        if session.connection.state is spotify.ConnectionState.LOGGED_IN:
            print 'Successfully logged in to Spotify.\n'
            logged_in_event.set()

    session = spotify.Session()
    loop = spotify.EventLoop(session)
    loop.start()
    session.on(
        spotify.SessionEvent.CONNECTION_STATE_UPDATED,
        connection_state_listener)
    session.login(spotify_username, spotify_password)

    return session, logged_in_event


def query_yes_no(default=None):
    """ Prompts user for yes/no input """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '{}'".format(default))

    while True:
        print prompt
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print 'Please respond with \'yes\' (y) or \'no\' (n)'
            print prompt


def normalize_string(value):
    """ Converts a string value to its appropriate encoding """
    try:
        unicode(value, 'ascii')
    except UnicodeError:
        value = unicode(value, 'utf-8')
    else:
        pass
    return value


def calculate_search_confidence(
    spotify_search, album, artist, found_album=None, found_artist=None):
    """ Uses fuzzywuzzy to determine similarity between Google Music album and
    artist and Spotify search results album and artist """
    if (spotify_search.album_total > 0 and found_album):
        album_confidence = fuzz.ratio(
            normalize_string(album), found_album.name)
    else:
        album_confidence = 0 # cannot add album without confidence

    if (spotify_search.artist_total > 0 and found_artist):
        artist_confidence = fuzz.ratio(
            normalize_string(artist), found_artist.name)
    else:
        artist_confidence = 50

    return (album_confidence + artist_confidence)/2


def do_migration(spotify_session, albums, playlist):
    """ Searches spotify for album:artist and adds to a new Spotify playlist.
    Does naive confidence checking based on fuzzy ratio matching (our searched
    term vs. what Spotify returned) and existence of both album and artist
    results being returned from Spotify"""
    migrated_tracks = 0

    for album, artist in albums:
        # only search if we have album chars
        if len(album) < 1:
            continue

        # setup spotify search
        search = spotify_session.search(
            'album:"{}" artist:"{}"'.format(album, artist))
        try:
            search.load()
        except spotify.Error, e:
            print 'Spotify error: {}'.format(e)

        found_album = None
        found_artist = None

        # load album and artist info from spotify if found
        if (search.album_total > 0):
            found_album = search.albums[0].load()
        else:
            print 'Search for {} by {} found no album results\n'.format(
                album, artist)
            continue

        if (search.artist_total > 0):
            found_artist = search.artists[0].load()

        # require user intervention if spotify doesnt match
        search_confidence = calculate_search_confidence(
            search, album, artist, found_album, found_artist)
        required_confidence = 75
        add_to_spotify = True

        if search_confidence < required_confidence:
            print 'Search for {} by {} found {} results with <{}% ' \
                  'confidence... add this album to spotify? ' \
                  '({}% confident)'.format(
                        album, artist,
                        (search.album_total + search.artist_total),
                        required_confidence, search_confidence)
            add_to_spotify = query_yes_no()

        if not add_to_spotify:
            print 'Ignoring low confidence search for {} by {}\n'.format(
                album, artist)
            continue

        # add album to spotify
        print '''Adding album {} by {} to Spotify with {}% confidence\n'''.format(
            album, artist, search_confidence)
        browser = found_album.browse().load()
        playlist.add_tracks(browser.tracks)
        total_album_tracks = len(browser.tracks)
        print '''Added {} tracks\n'''.format(total_album_tracks)
        migrated_tracks += total_album_tracks

    return migrated_tracks


def migrate_to_spotify():
    """Gathers tracks added to a users Google Music library. Adds them to an
    SQL database and retrieves unique album:artist rows to deduplicate the
    data. Then, searched Spotify for album:artist and adds the found tracks
    from the matching album to a playlist on the Spotify user's account """

    # spotify is async, start asap
    spotify_sess, spotify_logged_in_event = ask_for_spotify_session()
    gm_api = ask_for_google_music_api()

    print 'Successfully logged in to Google Music.\n'

    # Get all of the users tracks
    # library is a big list of dictionaries, each containing a single track
    print 'Loading Google Music library...',
    library = gm_api.get_all_songs()
    print 'done.\n'
    total_tracks = len(library)
    print '{} Google Music tracks detected.\n'.format(total_tracks)

    # Create db table
    conn = ask_for_db_connection()
    db = conn.cursor()
    db.execute(
        '''CREATE TABLE IF NOT EXISTS migrate_to_spotify
        (title text, artist text, album text)''')
    conn.commit()

    # insert google music tracks
    for track in library:
        t = (
            track['title'].encode('utf-8'),
            track['artist'].encode('utf-8'),
            track['album'].encode('utf-8'),
        )
        db.execute('INSERT INTO migrate_to_spotify VALUES (?,?,?)', t)
    conn.commit()

    # block further spotify operations until logged in or max 10 seconds
    spotify_logged_in_event.wait(10)

    # create a new playlist
    playlists = spotify_sess.playlist_container.load()
    playlist = playlists.add_new_playlist(
        'migrate to spotify {}'.format(datetime.now()))

    # dedupe album:artist
    albums = db.execute(
        '''SELECT DISTINCT album, artist FROM migrate_to_spotify''')
    albums = albums.fetchall()

    # process album:artist to spotify
    total_migrated_tracks = do_migration(spotify_sess, albums, playlist)

    # cleanup
    spotify_sess.logout()
    conn.close()
    gm_api.logout()
    print 'Successfully migrated {} out of {} ({}%) tracks to Spotify!'.format(
        total_migrated_tracks, total_tracks,
        (float(total_migrated_tracks) / float(total_tracks)) * 100)

if __name__ == '__main__':
    migrate_to_spotify()
