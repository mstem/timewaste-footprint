from flask import Flask, render_template, request
from dotenv import load_dotenv
import youtube

load_dotenv()

app = Flask(__name__)


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


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")
