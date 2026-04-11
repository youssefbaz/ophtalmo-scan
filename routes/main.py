from flask import Blueprint, render_template

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/medecin')
def login_medecin():
    return render_template('index.html')


@bp.route('/patient')
def login_patient():
    return render_template('index.html')
