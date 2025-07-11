from flask import Blueprint, render_template

scan_list_bp = Blueprint("scan_list", __name__)

@scan_list_bp.route("/", methods=["GET"])
def scan_list():
    return render_template("scan_list.html")
