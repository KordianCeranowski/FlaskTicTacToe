from flask import Flask, render_template, url_for, request, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from datetime import datetime
import pickle
from collections import defaultdict

# json.dumps(obj.__dict__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

@socketio.on('player_connected')
def player_connected(msg, methods=['GET', 'POST']):
    game = Game.query.get_or_404(msg['game_id'])
    if  len(game.get_players_register()) < game.players_count and \
        msg['player_id'] not in game.get_players_register():
        game.set_players_register(msg['player_id'], msg['emoji'])
    print(game.get_players_register())
    socketio.emit('player_connected', {
        'game_id': msg['game_id'],
        'joined_players_emojis': ' '.join(game.get_players_register().values())
    })

@socketio.on('pressed_cell')
def pressed_cell(msg, methods=['GET', 'POST']):
    id = int(msg['game_id'])
    row = int(msg['row'])
    col = int(msg['col'])
    game = Game.query.get_or_404(id)
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
    socketio.emit('pressed_cell', {
        'game_id': id,
        'row': row,
        'col': col,
        'sign': sign,
        'next_sign': game.current_player_sign(),
        'round': game.round
    })

@socketio.on('created_game')
def create_game(msg, methods=['GET', 'POST']):
    try:
        errors = []
        rows = int(msg['rows'])
        cols = int(msg['cols'])
        goal = int(msg['goal'])
        players_count = int(msg['players_count'])
    except (ValueError, TypeError):
        errors = ['One of values was not an integer']
    if rows not in range(3,100) or cols not in range(3,100):
        errors += ['Rows or columns size out of 3-100 bounds']
    if goal > rows and goal > cols:
        errors += ['Goal too high']
    if goal < 3:
        errors += ['Goal too low']
    if players_count < 2:
        errors += ['Not enough players_count']

    if not errors:
        new_game = Game(rows, cols, goal, players_count)
        try:
            db.session.add(new_game)
            db.session.commit()
            id = Game.query.order_by(Game.date_created.desc()).first().id
        except:
            errors += ['Error while saving to database']

    print(errors)
    if not errors:
        socketio.emit('game_create_success', {
            'id': id,
            'rows': rows,
            'cols': cols,
            'goal': goal,
            'players_count': players_count
        })
    else:
        socketio.emit('game_create_failure', {
            'errors': errors
        })

@socketio.on('deleted_game')
def delete_game(msg, methods=['GET', 'POST']):
    errors = []
    game_to_delete = Game.query.get_or_404(msg['id'])
    try:
        db.session.delete(game_to_delete)
        db.session.commit()
    except:
        errors += ['Error while saving to database']

    if not errors:
        socketio.emit('game_delete_success', {
            'id': msg['id']
        })
    else:
        socketio.emit('game_delete_failure', {
            'errors': errors
        })

@app.route('/')
def index():
    games = Game.query.order_by(Game.date_created).all()
    # śmieszny easter egg
    resp = make_response(render_template('index.html', games=games))
    resp.set_cookie('ciastko', 'jebac pis')
    return resp

@app.route('/game/<int:id>')
def run_game(id):
    game_to_play = Game.query.get_or_404(id)
    return render_template('game.html', game=game_to_play)


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
            return f"Waiting for players: {len(self.get_players_register())}/{self.players_count}"
        if self.winner != '_':
            return f"In progress. Round: {self.round}"
        return f"Game ended. Winner: {self.winner}"

if __name__ == '__main__':
    app.run(debug=True)
