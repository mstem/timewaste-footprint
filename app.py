import os
import secrets
from flask import Flask, render_template, request, redirect, session, url_for
from dotenv import load_dotenv
import youtube
import tiktok

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def _redirect_uri():
    base = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
    return f"{base}/tiktok/callback"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    handle = (request.form.get("handle") or "").strip().lstrip("@")
    if not handle:
        return render_template("index.html", error="Please enter a channel handle.")
    try:
        results = youtube.analyze_channel(handle, max_videos=50)
        return render_template("index.html", results=results, handle=handle)
    except ValueError as e:
        return render_template("index.html", error=str(e))
    except LookupError as e:
        return render_template("index.html", error=str(e))
    except PermissionError as e:
        return render_template("index.html", error=str(e))
    except Exception as e:
        return render_template("index.html", error=f"Something went wrong: {e}")


@app.route("/tiktok/connect")
def tiktok_connect():
    try:
        code_verifier, code_challenge = tiktok.generate_pkce()
        state = secrets.token_urlsafe(16)
        session["tt_state"] = state
        session["tt_verifier"] = code_verifier
        auth_url = tiktok.build_auth_url(state, code_challenge, _redirect_uri())
        return redirect(auth_url)
    except ValueError as e:
        return render_template("index.html", tt_error=str(e))


@app.route("/tiktok/callback")
def tiktok_callback():
    error = request.args.get("error")
    if error:
        return render_template("index.html", tt_error=f"TikTok login cancelled or failed.")

    code = request.args.get("code")
    state = request.args.get("state")

    if not code or state != session.get("tt_state"):
        return render_template("index.html", tt_error="Invalid OAuth state. Please try again.")

    try:
        access_token = tiktok.exchange_code(code, session.pop("tt_verifier", ""), _redirect_uri())
        session.pop("tt_state", None)
        results = tiktok.analyze_account(access_token)
        return render_template("index.html", results=results)
    except Exception as e:
        return render_template("index.html", tt_error=f"Something went wrong: {e}")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")
