# <editor-fold SETUP>

from flask import Flask, render_template, url_for, request, redirect, make_response, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from datetime import datetime
import pickle
from collections import defaultdict
import json
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vnkdjnfjknfl1232#'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

# </editor-fold>

# <editor-fold MENU

@app.route('/')
def index():
    games = Game.query.order_by(Game.date_created).all()
    return render_template('index.html', games=games)

@socketio.on('player_joined_menu')
def player_joined_menu(msg, methods=['GET, POST']):
    socketio.emit('update_menu', Game.all_to_json(), room=request.sid)

@socketio.on('created_game')
def create_game(msg, methods=['GET', 'POST']):
    try:
        errors = []
        rows = int(msg['rows'])
        cols = int(msg['cols'])
        goal = int(msg['goal'])
        players_count = int(msg['players_count'])
    except (ValueError, TypeError):
        errors += ['One of values was not an integer']
        flash('One of values was not an integer', 'error')
    if rows not in range(3,100) or cols not in range(3,100):
        errors += ['Rows or columns size out of 3-100 bounds']
        flash('Rows or columns size out of 3-100 bounds', 'error')
    if goal > rows and goal > cols:
        errors += ['Goal too high']
        flash('Goal too high', 'error')
    if goal < 3:
        errors += ['Goal too low']
        flash('Goal too low', 'error')
    if players_count < 1:
        errors += ['Not enough players_count']
        flash('Not enough players_count', 'error')
    if not errors:
        new_game = Game(rows, cols, goal, players_count)
        try:
            db.session.add(new_game)
            db.session.commit()
            id = Game.query.order_by(Game.date_created.desc()).first().id
        except:
            errors += ['Error while saving to database']
    else:
        return redirect('/')
    print(f'creating game, errors: {errors}')
    if not errors:
        print(f'sending update_menu with {Game.all_to_json()}')
        socketio.emit('update_menu', Game.all_to_json())

@socketio.on('deleted_game')
def delete_game(msg, methods=['GET', 'POST']):
    print(f"recived deleted_game with {msg}")
    errors = []
    game_to_delete = Game.query.get_or_404(msg['id'])
    try:
        db.session.delete(game_to_delete)
        db.session.commit()
    except:
        errors += ['Error while saving to database']

    print(f'removed game with id:{msg["id"]}, errors:{errors}')
    if not errors:
        print('sending updated_menu')
        socketio.emit('update_menu', Game.all_to_json())

# </editor-fold>

# <editor-fold GAME
@app.route('/game/<int:id>')
def run_game(id):
    game = Game.query.get_or_404(id)
    if 'emoji-unicode' not in request.cookies:
        flash('Please choose your emoji first', 'error')
        return redirect('/')
    emoji = request.cookies['emoji-unicode'].replace('%3B', ';')
    session_id = request.cookies['session_id']
    print(session_id)
    print(emoji)
    print(game.get_players_register())
    if session_id in game.get_players_register() or emoji not in game.get_players_register().values():
        return render_template('game.html', id=game.id, rows=game.rows, cols=game.cols)
    flash('Someone already uses your emoji in this game, please switch it so something other', 'error')
    return redirect('/')

@socketio.on('player_joined_game')
def player_connected(msg, methods=['GET', 'POST']):
    print(f"recived player_joined_game from {msg['player_id']} {msg['emoji']}")
    game = Game.query.get_or_404(msg['game_id'])
    if len(game.get_players_register()) < game.players_count and msg['player_id'] not in game.get_players_register():
        print('\tadded player to register')
        game.set_players_register(msg['player_id'], msg['emoji'])
        print('\temitting update_menu')
        socketio.emit('update_menu', Game.all_to_json())
    print(f'\tregister contains: {game.get_players_register()}')
    print('\temitting update_game')
    socketio.emit('update_game', game.to_json())


@socketio.on('pressed_cell')
def pressed_cell(msg, methods=['GET', 'POST']):
    print('recived pressed_cell')
    id = int(msg['game_id'])
    row = int(msg['row'])
    col = int(msg['col'])
    game = Game.query.get_or_404(id)
    if 'in_progress' not in game.get_state():
        print(f'gamestate is {game.get_state()}')
        return
    if msg['player_id'] != list(game.get_players_register().keys())[game.current_player_id()]:
        print(f'Its another players turn')
        return
    if (row, col) in game.get_board():
        print('Field already pressed')
        return
    sign = game.current_player_sign()
    game.set_board(row, col, game.current_player_sign())
    if game.has_won(row, col, game.goal, sign):
        game.winner = sign
    if game.is_draw():
        game.winner = 'DRAW'
    game.round += 1
    try:
        db.session.commit()
    except:
        print('Error while saving gamestate')
    print('emitting update_game')
    socketio.emit('update_game', game.to_json())


# </editor-fold>


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer)
    cols = db.Column(db.Integer)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    board = db.Column(db.PickleType)
    players_register = db.Column(db.PickleType)
    players_count = db.Column(db.Integer)
    round = db.Column(db.Integer)
    winner = db.Column(db.String(4), default=' ')
    goal =  db.Column(db.Integer)

    def to_json(self):
        json =  str('{\n' + f'\
                "id": {self.id}, \
                "rows": {self.rows}, \
                "cols": {self.cols},   \
                "goal": {self.goal}, \
                "players_count": {self.players_count}, \
                "players_joined": {len(self.get_players_register())}, \
                "state": "{self.get_state()}", \
                "round": {self.round}, \
                "winner": "{str(self.winner)}", \
                "emojis": {str(list(self.get_players_register().values()))}, \
                "board": {str({str(key): str(self.get_board()[key]) for key in self.get_board()})} \
                '+ '}')
        return re.sub(r"'", "\"", re.sub(r"[\s\t]*", "", json))

    def all_to_json():
        games = [game.to_json() for game in Game.query.all()]
        games = '{"games": [' + ','.join(games) + "]}"
        return games

    def default_value():
        return '_'

    def __init__(self, rows, cols, goal, players_count):
        self.rows = rows
        self.cols = cols
        self.goal = goal
        self.players_count = players_count
        self.round = 0
        board = defaultdict(Game.default_value)
        self.board = pickle.dumps(board)
        self.players_register = pickle.dumps({})

    def set_board(self, row, col, val):
        self.board = pickle.loads(self.board)
        self.board[(row, col)] = val
        self.board = pickle.dumps(self.board)

    def get_board(self):
        return pickle.loads(self.board)

    def set_players_register(self, id, emoji):
        players_register = pickle.loads(self.players_register)
        players_register[id] = emoji
        self.players_register = pickle.dumps(players_register)
        db.session.commit()

    def get_players_register(self):
        return pickle.loads(self.players_register)

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

    def current_player_sign(self):
        if (len(self.get_players_register()) < self.players_count):
            return "Waiting"
        return list(self.get_players_register().values())[self.current_player_id()]

    def current_player_id(self):
        return self.round % self.players_count

    def get_state(self):
        if len(self.get_players_register()) < self.players_count:
            return "waiting_for_players"
        print(f'winner: {self.winner} {self.winner==" "}')
        if self.winner == ' ':
            return f"in_progress"
        return f"ended"

if __name__ == '__main__':
    app.run(ssl_context='adhoc')
