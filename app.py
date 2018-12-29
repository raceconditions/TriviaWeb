import socketio
import eventlet
from flask import Flask, render_template, jsonify, request
import requests
import time
from threading import Timer
import uuid

bio = socketio.BaseManager()
sio = socketio.Server(client_manager=bio)
app = Flask(__name__)

users = {}
games = {}

seconds_per_question = 15;
number_of_questions = 10;

@app.route('/')
def index():
    """Serve the client-side application."""
    return render_template('app.html')

@app.route('/categories')
def categories():
    r = requests.get('https://opentdb.com/api_category.php')
    return jsonify(r.text)

@app.route('/answer', methods=['POST'])
def answer_question():
    r = request.get_json()
    room = r['room']
    answer = r['answer']
    sid = r['sid']
    index = r['index']
    if(games[room][index]['answer'] == answer):
        if(sid not in games[room][index]['correct_sids']):
            games[room][index]['correct_sids'].append(sid)
    print(games[room][index]['correct_sids'])


    return ''

@sio.on('connect')
def connect(sid, environ):
    print('connect ', sid)

@sio.on('disconnect')
def disconnect(sid):
    print('disconnect ', sid)

@sio.on('my event', namespace='/test')
def test_message(sid, message):
    sio.emit('my response', {'data': message['data']}, room=sid,
                   namespace='/test')

@sio.on('my broadcast event', namespace='/test')
def test_broadcast_message(sid, message):
    sio.emit('my response', {'data': message['data']}, namespace='/test')

@sio.on('start', namespace='/test')
def start(sid, message):
    games[message['room']] = {}
    print('starting')
    r = requests.get('https://opentdb.com/api.php?amount=' + str(number_of_questions) + '&category=' + message['category'])
    results = r.json()['results']
    next = 0
    for q in results:
        sio.start_background_task(send_question, *(next,q,message['room']))
        next = next + seconds_per_question
    sio.start_background_task(finish_game, *(next, message['room']))

def send_question(when, q, room):
    sio.sleep(when)
    index = str(uuid.uuid4())
    games[room][index] = {}
    games[room][index]['answer'] = q['correct_answer']
    games[room][index]['correct_sids'] = []
    sio.emit('question', {'time': seconds_per_question, 'question': q['question'], 'incorrect_answers': q['incorrect_answers'], 'correct_answer': q['correct_answer'], 'index': index}, room=room,
              namespace='/test')

def finish_game(when, room):
    sio.sleep(when)
    results = {}
    for q in games[room]:
        for s in games[room][q]['correct_sids']:
            if(users[s] in results):
                results[users[s]] = results[users[s]] + 1
            else:
                results[users[s]] = 1
    ar = []
    for r in results:
        ar.append({'user':r, 'count':results[r]})
    sio.emit('results', {'results': ar}, room=room,
              namespace='/test')


   

@sio.on('join', namespace='/test')
def join(sid, message):
    users[sid] = message['username']
    print('join ', message['room'], users[sid])
    sio.enter_room(sid, message['room'], namespace='/test')
    sio.emit('joined room', {'sid': sid, 'username': users[sid]},
                   room=message['room'], namespace='/test')
    participants = bio.get_participants('/test', message['room'])
    for p in participants:
        print(p)
        sio.emit('joined room', {'sid': p, 'username': users[p]},
                   room=sid, namespace='/test')


@sio.on('leave', namespace='/test')
def leave(sid, message):
    del users[sid]
    sio.leave_room(sid, message['room'], namespace='/test')
    sio.emit('left room', {'sid': sid, 'username': users[sid]},
                   room=message['room'], namespace='/test')


@sio.on('close room', namespace='/test')
def close(sid, message):
    del users[sid]
    sio.emit('closing room',
                   {},
                   room=message['room'], namespace='/test')
    sio.close_room(message['room'], namespace='/test')


@sio.on('my room event', namespace='/test')
def send_room_message(sid, message):
    sio.emit('message', {'username': users[sid], 'data': message['data']},
                   room=message['room'], namespace='/test')


@sio.on('disconnect request', namespace='/test')
def disconnect_request(sid):
    sio.disconnect(sid, namespace='/test')
    del users[sid]

if __name__ == '__main__':
    # wrap Flask application with socketio's middleware
    app = socketio.Middleware(sio, app)

    # deploy as an eventlet WSGI server
    eventlet.wsgi.server(eventlet.listen(('', 8000)), app)
