# routes/home.py

from flask import session
from flask import Blueprint, render_template, redirect, session

home_bp = Blueprint("home", __name__)

# '/'와 '/home' 둘 다 접근 가능하도록 설정
@home_bp.route("/")
@home_bp.route("/home")
def home():
     if "user_id" not in session:
        return redirect("/auth/login")
     return render_template("home.html")