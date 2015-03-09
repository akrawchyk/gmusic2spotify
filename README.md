# gmusic2spotify

Simple Python script to migrate albums from a Google Music library to a Spotify playlist. It uses an in memory sqlite database for deduplicating albums by selecting distinct album:artist combinations from the discovered tracks in a Google Music Library. Then it searches Spotify using [refined queries](https://news.spotify.com/us/2008/01/22/searching-spotify/) (e.g. 'album:"Untrue" artist:"Burial"'), tests the confidence of the first Spotify search result for album and artist, then adds the album's tracks to new a Spotify playlist.

Caveats:

* One playlist is created each time the script is invoked. This playlist is named `migrate to spotify <datetime.now()>`
* Does not add tracks if no albums are included in Spotify's search results, regardless if an artist is found
* Requires user intervention if search confidence is below 75%

TODO:

* Save list of unmigrated tracks
* Support adding single tracks, not just whole albums


## Requirements

Required Python packages are included in `requirements.txt` and can be installed by calling `pip install -r requirements.txt` from the root of this project. Details related to these packages are as follows:

* `pyspotify` ([installation documentation](https://pyspotify.mopidy.com/en/latest/installation/))
* `gmusicapi` ([installation documentation](http://unofficial-google-music-api.readthedocs.org/en/latest/usage.html#usage))

You also need accounts for access to the services apis.

* Google Music account with >0 tracks
* Spotify Premium account (required to [make Spotify api calls with pyspotify](https://pyspotify.mopidy.com/en/latest/quickstart/#login-and-event-processing))

**NOTE:** The `gmusicapi` library [does not support Google's 2-factor authentication](https://github.com/simon-weber/Unofficial-Google-Music-API/issues/168). If you have 2-factor authentication enabled on your Google account, you can create an app-specific password for this script [on Google's account dashboard](https://security.google.com/settings/security/apppasswords) as a workaround.


## Usage

Update the script with your account credentials. Then invoke the script with:

`./migrate_to_spotify.py`

During processing, the script does naive confidence checking of the quality of Spotify search results. To determine the confidence that the Spotify results match the Google Music album, it applies a confidence score of the first Spotify result relative to the search term provided (i.e. does the album name from Google Music match the album name from Spotify). This is a naive confidence assignment using [`fuzzywuzzy`'s ratio function](https://github.com/seatgeek/fuzzywuzzy#simple-ratio).

It will block the migration process if this score is below 75%, and requires user intervention to continue. To avoid user intervention, pipe 'y' into the script invocation with:

`yes | ./migrate_to_spotify.py`
