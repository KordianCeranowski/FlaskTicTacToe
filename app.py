from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pickle
from collections import defaultdict

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer)
    cols = db.Column(db.Integer)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    board = db.Column(db.PickleType)
    players = db.Column(db.Integer)
    round = db.Column(db.Integer)
    winner = db.Column(db.String(4), default=' ')
    goal =  db.Column(db.Integer)

    def default_value():
        return '_'

    def __init__(self, rows, cols, goal, players):
        self.rows = rows
        self.cols = cols
        self.goal = goal
        self.players = players
        self.round = 0
        board = defaultdict(Game.default_value)
        self.board = pickle.dumps(board)

    def set_board(self, row, col, val):
        self.board = pickle.loads(self.board)
        self.board[(row, col)] = val
        self.board = pickle.dumps(self.board)

    def get_board(self):
        return pickle.loads(self.board)

    def __repr__(self):
        return f'Game: id={self.id}, date={self.date_created}, board={self.get_board()},'


    def get_pattern(self, row, col, size, func):
        board = self.get_board()
        arr = [board[func(row, col, diff)] for diff in range(-size + 1, size)]
        return ''.join(arr)

    def get_all_patterns(self, row, col, size):
        funcs = [
                    lambda r, c, d: (r + d, c),     # vertical
                    lambda r, c, d: (r, c + d),     # horizontal
                    lambda r, c, d: (r + d, c + d), # crosswise
                    lambda r, c, d: (r - d, c + d)  # counter crosswise
                ]
        return [self.get_pattern(row, col, size, fun) for fun in funcs]

    def has_won(self, row, col, size, sign):
        patterns = self.get_all_patterns(row, col, size)
        winning_pattern = sign * size
        return any([winning_pattern in pattern for pattern in patterns])

    def is_draw(self):
        return len(self.get_board().keys()) == self.rows * self.cols

    player_signs = ['😂', '🐒', '👣', '🤔', '💋']

    def current_player_sign(self):
        return Game.player_signs[self.round % self.players]

    def current_player_id(self):
        return self.round % self.players


@app.route('/', methods=['POST', 'GET'])
def index():
    if request.method =='POST':
        try:
            rows = int(request.form['rows'])
            cols = int(request.form['cols'])
            goal = int(request.form['goal'])
            players = int(request.form['players'])
        except (ValueError, TypeError):
            return 'One of values was not an integer'

        if goal > rows and goal > cols:
            return 'Goal too high'

        if goal < 3:
            return 'Goal too low'

        if players > len(Game.player_signs):
            return 'Too many players'

        if players < 2:
            return 'Not enough players'

        new_game = Game(rows, cols, goal, players)

        try:
            db.session.add(new_game)
            db.session.commit()
            return redirect('/')
        except:
            return 'Error while loading menu'
    else:
        games = Game.query.order_by(Game.date_created).all()
        return render_template('index.html', games=games)


@app.route('/delete/<int:id>')
def delete(id):
    game_to_delete = Game.query.get_or_404(id)
    try:
        db.session.delete(game_to_delete)
        db.session.commit()
        return redirect('/')
    except:
        return 'Error while deleting game'


@app.route('/game/<int:id>', methods=['GET', 'POST'])
def run_game(id):
    game_to_play = Game.query.get_or_404(id)
    if request.method == 'POST':
        pass
    else:
        return render_template('game.html', game=game_to_play)


@app.route('/game/<int:id>/row/<int:row>/col/<int:col>', methods=['GET', 'POST'])
def press(id, row, col):
    game = Game.query.get_or_404(id)
    game.set_board(row, col, game.current_player_sign())

    if game.has_won(row, col, game.goal, game.current_player_sign()):
        game.winner = game.current_player_sign()

    if game.is_draw():
        game.winner = 'DRAW'

    game.round += 1

    try:
        db.session.commit()
    except:
        return 'Error while sign'
    # return run_game(id)
    return redirect(f'/game/{id}')

if __name__ == '__main__':
    app.run(debug=False)
