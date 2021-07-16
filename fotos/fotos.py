#!/usr/bin/env python3
import json
import os
import logging, logging.config

from db import Db
from albumParser import AlbumParser


from flask import Flask, redirect, request, url_for, render_template, send_file, make_response, send_from_directory, session
from oauthlib.oauth2 import WebApplicationClient
import requests
from werkzeug.exceptions import HTTPException

scriptPath = os.path.dirname(os.path.abspath(__file__))
config = json.load(open(os.path.join(scriptPath, 'config.json'), 'r'))
logging.config.dictConfig(config['logging'])
logger = logging.getLogger('fotos')


# Flask app setup
app = Flask(__name__)
app.secret_key = config["flaskSecret"]

# OAuth2 client setup
client = WebApplicationClient(config['googleOauth']['clientId'])

parser = AlbumParser(config, logger)
db = Db(config, logger)

def login(initial_url):
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Use library to construct the request for login and provide
    # scopes that let you retrieve user's profile from Google
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.url_root + "login/callback",
        scope=["openid", "email", "profile"],
        state=initial_url
    )
    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")
    state = request.args.get("state")

    # Find out what URL to hit to get tokens that allow you to ask for
    # things on behalf of a user
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    # Prepare and send request to get tokens! Yay tokens!
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(config['googleOauth']['clientId'], config['googleOauth']['clientSecret']),
    )

    # Parse the tokens!
    client.parse_request_body_response(json.dumps(token_response.json()))

    # Now that we have tokens (yay) let's find and hit URL
    # from Google that gives you user's profile information,
    # including their Google Profile Image and Email
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    # We want to make sure their email is verified.
    # The user authenticated with Google, authorized our
    # app, and now we've verified their email through Google!
    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        picture = userinfo_response.json()["picture"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400

    user = db.get_user(users_email)

    if not user:
        raise Exception("Missing user %s" % id) 
    else:
        logger.info("Login user: %s %s" % user)

    # Begin user session by logging the user in
    session.permanent = False #https://stackoverflow.com/questions/37227780/flask-session-persisting-after-close-browser
    session['user'] = {'email': users_email, 'tags': user[1], 'name': users_name, 'picture': picture } 

    # Send user back to initial requested url
    return redirect(state)

@app.route("/logout")
def logout():
    del session['user']
    return redirect(url_for("index"))

def get_google_provider_cfg():
    return requests.get(config['googleOauth']['discoveryURL']).json()

def authenticate():
    if 'user' in session:
        current_user = session['user']
        logger.info("%s is authenticated" % current_user)
        return current_user, None
    else:
        logger.info("Not authenticated")
        return None, login(request.full_path)

@app.after_request
def add_header(r):
    """
    disable caching
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(e, exc_info = 1)
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    return render_template("error.html", e=e), 403

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/parse")
def parse():
    """
    parse a folder to create an album
    """
    user, redirect_response = authenticate()
    if not user:
        return redirect_response
    user_tags = user['tags']

    if not 'admin' in user_tags:
        raise Exception("Admin required for parse operation")
    path = request.args.get('path', None)
    force = request.args.get('force', 'false')
    force = (force == 'true')
    album = parser.parse(path, force)
    db.create_album(album, force)
    return redirect(url_for('album', album = album['name']))

@app.route("/import")
def import_album():
    """
    import a generated album from it's json file
    """
    user, redirect_response = authenticate()
    if not user:
        return redirect_response
    user_tags = user['tags']

    if not 'admin' in user_tags:
        raise Exception("Admin required for import operation")
    path = request.args.get('path', None)
    album = parser.import_album(path)
    db.create_album(album, True)
    redirect_url = url_for('album', album = album['name'])
    logger.info("Redirecting to: %s" % redirect_url)
    return redirect(redirect_url)

@app.route("/<album>")
def album(album):
    user, redirect_response = authenticate()
    if not user:
        return redirect_response
    user_tags = user['tags']

    result = db.search_photos(album, user_tags)
    if result:
        for photo in result['photos']:
            style = ''
            if photo['thumb_width'] != config['thumbSizeSmall']:
                style = 'width:%spx; ' % (int(photo['thumb_width']) + 6)
            if photo['thumb_height'] != config['thumbSizeSmall']:
                style = style + 'height:%spx; ' % (int(photo['thumb_height']) + 6)
            photo['style'] = style
        return render_template('album.html', data = result, config = config, user = user)
    else:
        raise Exception("Missing album %s" % album)

@app.route("/css/album.css")
def album_css():
    response = make_response(render_template('album.css', config = config))
    response.headers['Content-type'] = 'text/css; charset=utf-8'
    return response

@app.route("/<album>/<photo>")
def photo(album, photo):
    return _photo(album, photo)

@app.route("/<album>/thumbs/<photo>")
def thumb(album, photo):
    return _photo(album, photo, True)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

def _photo(album, photo, thumb = False):
    user, redirect_response = authenticate()
    if not user:
        return redirect_response
    user_tags = user['tags']

    result = db.search_photo(album, photo, user_tags)
    if thumb:
        photo_file = os.path.join(result[0], result[1], config['albumDir'], config['thumbDir'], result[2])
    else:
        photo_file = os.path.join(result[0], result[1], config['albumDir'], result[2])
    return send_file(photo_file)

@app.route("/tag/<tag>")
def tags(tag):
    return 'tag %s' % tag

if __name__ == '__main__':
    app.run()