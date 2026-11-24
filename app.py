import re
import sys
sys.path.append("src")

from flask import Flask, render_template, request, jsonify
import markdown

import config
from utils import warm_up
from stage1_requirements import generate_requirements
from stage2_sdlc import choose_sdlc

app = Flask(__name__)


def to_html(text):
    return markdown.markdown(text, extensions=["tables", "fenced_code"])


@app.route("/")
def home():
    return render_template("index.html", model=config.MODEL)


@app.route("/stage1", methods=["POST"])
def stage1():
    data = request.get_json(silent=True) or {}
    functionality = (data.get("functionality") or "").strip()
    if not functionality:
        return jsonify(error="Please enter a functionality."), 400
    try:
        text = generate_requirements(functionality)
    except Exception as e:
        return jsonify(error=f"Stage 1 failed: {e}"), 500
    return jsonify(markdown=text, html=to_html(text))


@app.route("/stage2", methods=["POST"])
def stage2():
    data = request.get_json(silent=True) or {}
    requirements = (data.get("requirements") or "").strip()
    if not requirements:
        return jsonify(error="No requirements to analyse."), 400
    try:
        text = choose_sdlc(requirements)
    except Exception as e:
        return jsonify(error=f"Stage 2 failed: {e}"), 500
    match = re.search(r"Recommended SDLC:\s*\**\s*(.+)", text)
    name = match.group(1).strip(" *") if match else ""
    return jsonify(html=to_html(text), sdlc=name)


if __name__ == "__main__":
    print(f"Loading {config.MODEL} into memory ...")
    warm_up()   # first request is no longer slowed by model loading
    app.run(host="127.0.0.1", port=5000, debug=False)