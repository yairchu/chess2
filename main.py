'''
A networked real-time strategy game based on Chess
'''

import marshal
import random
import select
import socket
import time
import threading
import urllib.request

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
import stun

import env
from board_view import BoardView
from game_model import GameModel
from widgets import WrappedLabel

num_msg_lines = 6

def poll(sock):
    return select.select([sock], [], [], 0)[0] != []


latency = 5

def quiet_action(func):
    func.quiet = True
    return func

class Game(BoxLayout):
    def __init__(self, **kwargs):
        super(Game, self).__init__(**kwargs)
        self.game_model = GameModel()
        self.game_model.king_captured = self.king_captured
        self.done = False
        self.instance_id = random.randrange(2**64)
        self.nicknames = {}
        self.address = None
        self.messages = []
        self.last_start = 0
        self.iter_actions = {}
        self.peers = []
        self.last_selected_at_dst = {}
        self.is_replay = False
        self.socket = None
        self.threads = []
        self.score = [0, 0]
        net_thread = threading.Thread(target=self.net_thread_go)
        self.threads.append(net_thread)
        if not env.dev_mode:
            net_thread.start()

        self.board_view = BoardView(self.game_model)
        self.add_widget(self.board_view)

        self.info_pane = BoxLayout(orientation='vertical')
        self.add_widget(self.info_pane)

        row = 60
        self.score_label = WrappedLabel(
            halign='center',
            size_hint=(1, 0),
            size_hint_min_y=row)
        self.info_pane.add_widget(self.score_label)

        self.label = WrappedLabel(halign='center', valign='bottom')
        self.info_pane.add_widget(self.label)

        self.text_input = TextInput(
            multiline=False,
            text_validate_unfocus=env.is_mobile,
            size_hint=(1, 0),
            size_hint_min_y=row)
        self.text_input.bind(on_text_validate=self.handle_text_input)
        if not env.is_mobile:
            def steal_focus(*args):
                if not self.text_input.focus:
                    self.text_input.focus = True
            self.text_input.bind(focus=steal_focus)
        self.info_pane.add_widget(self.text_input)

        self.action_reset(self.instance_id)

        self.messages.append('')
        self.messages.append('Welcome to Chess 2!')
        self.messages.append('Developer Mode' if env.dev_mode else 'Establishing server connection...')
        self.update_label()

        self.bind(size=self.resized)
        Clock.schedule_interval(self.on_clock, 1/30)

    def update_label(self):
        self.score_label.text = 'White: %d   Black: %d' % tuple(self.score)
        self.label.text = '\n'.join(self.messages[-num_msg_lines:])

    def resized(self, _widget, size):
        self.orientation = 'horizontal' if size[0] > size[1] else 'vertical'
        p = 1/3
        self.info_pane.size_hint = (p, 1) if self.orientation == 'horizontal' else (1, p)

    def net_thread_go(self):
        self.setup_socket()
        if self.done:
            return
        self.setup_addr_name()
        if self.done:
            return
        self.wait_for_connections()

    def setup_socket(self):
        while True:
            local_port = random.randint(1024, 65535)
            try:
                if self.done:
                    return
                _nat_type, gamehost, gameport = stun.get_ip_info('0.0.0.0', local_port)
                if gameport is None:
                    print('retrying stun connection')
                    continue
                self.my_addr = (gamehost, gameport)
                print('external host %s:%d' % self.my_addr)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('', local_port))
                print('listening on port %d' % local_port)
            except socket.error:
                print('retrying establishing server')
                continue
            break
        self.socket = sock

    def setup_addr_name(self):
        url = 'http://game-match.herokuapp.com/register/chess2/%s/%d/' % self.my_addr
        print('registering at %s' % url)
        self.address = urllib.request.urlopen(url).read().decode('utf-8')
        self.messages.append('')
        self.messages.append('Your address is:')
        self.messages.append(self.address.upper())
        self.messages.append('')
        self.messages.append('Type the address of a friend to play with them')
        self.update_label()

    def wait_for_connections(self):
        while not self.peers:
            time.sleep(5)
            if self.done:
                return
            url = 'http://game-match.herokuapp.com/lookup/chess2/%s/' % self.address.replace(' ', '%20')
            print('checking game at %s' % url)
            self.add_peers(urllib.request.urlopen(url).read().decode('utf-8'))

    def add_peers(self, peers_str):
        for x in peers_str.split():
            host, port_str = x.split(':')
            port = int(port_str)
            if (host, port) == self.my_addr:
                continue
            if (host, port) in self.peers:
                continue
            print('established connection with %s:%d' % (host, port))
            self.peers.append((host, port))
            self.game_model.started = True
            self.messages.clear()
            self.messages.append('')
            self.messages.append('Connection successful!')
            self.messages.append('THE GAME BEGINS!')
            self.update_label()

    def nick(self, i):
        return self.nicknames.get(i, 'anonymouse')

    def handle_text_input(self, entry):
        command = entry.text
        entry.text = ''
        if not command:
            return
        if command[:1] == '/':
            self.game_model.add_action(*command[1:].split())
            return
        if self.peers or env.dev_mode:
            # Chat
            self.game_model.add_action('msg', command)
            return
        connect_thread = threading.Thread(target=self.connect_thread_go, args=(command, ))
        self.threads.append(connect_thread)
        connect_thread.start()

    def connect_thread_go(self, addr):
        while self.address is None:
            # Net thread didn't finish
            time.sleep(1)
        url = 'http://game-match.herokuapp.com/connect/chess2/%s/%s/' % (self.address.replace(' ', '%20'), addr.replace(' ', '%20'))
        print('looking up host at %s' % url)
        self.add_peers(urllib.request.urlopen(url).read().decode('utf-8'))
        self.game_model.player = 1

    @quiet_action
    def action_nick(self, i, *words):
        name = '-'.join(words)
        if not name:
            name = 'null-boy'
        self.messages.append(self.nick(i) + ' is now ' + name)
        self.nicknames[i] = name

    @quiet_action
    def action_msg(self, i, *txt):
        self.messages.append('%s: %s' % (self.nick(i), ' '.join(txt)))

    @quiet_action
    def action_move(self, _id, src, dst):
        if src not in self.game_model.board:
            return
        self.game_model.board[src].move(dst)

    def action_reset(self, _id, num_boards=1):
        self.game_model.init(int(num_boards))
        self.board_view.reset()
        self.potential_pieces = []

    def action_replay(self, i):
        self.iter_actions[self.game_model.counter][i] = [('endreplay', ())]
        self.replay_counter = self.last_start
        self.action_reset(i, self.num_boards)
        self.is_replay = True

    def action_endreplay(self, _id):
        self.is_replay = False

    def player_str(self, player):
        if player is None:
            return 'spectator'
        r = ['White', 'Black'][player%2]
        if self.game_model.num_boards > 1:
            r += '#'+str(player//2)
        return r

    @quiet_action
    def action_become(self, i, player):
        player = int(player)
        if i == self.instance_id:
            self.game_model.player = player
        self.messages.append(self.nick(i) + ' becomes ' + self.player_str(player))

    def action_credits(self, _id):
        self.messages.extend('''Credits:
        Programming: Yair Chuchem
        Chess sets/Graphics: Armondo H. Marroquin and Eric Bentzen (http://www.enpassant.dk/chess/fonteng.htm)
        Logic/Concept: Ancient People, Yair Chuchem, and fellow Play-Testers
        Programming Infrastructure: Python (Guido van Rossum and friends), Pygame/SDL (Pete Shinners and friends)
        '''.split('\n'))

    def action_help(self, _id):
        self.messages.append('commands: /help | /reset | /nick <nickname> | /replay | /credits')

    def communicate(self):
        if self.socket is None:
            return
        packet = marshal.dumps((
            self.instance_id,
            [(i, self.iter_actions.setdefault(i, {}).setdefault(self.instance_id, []))
                for i in range(max(0, self.game_model.counter-latency), self.game_model.counter+latency)]))
        for peer in self.peers:
            self.socket.sendto(packet, 0, peer)
        while poll(self.socket):
            packet, peer = self.socket.recvfrom(0x1000)
            peer_id, peer_iter_actions = marshal.loads(packet)
            for i, actions in peer_iter_actions:
                self.iter_actions.setdefault(i, {})[peer_id] = actions

    def king_captured(self, who):
        winner = 1 - who%2
        self.score[winner] += 1
        self.game_model.init(self.game_model.num_boards)
        self.board_view.reset()
        self.messages.append('')
        self.messages.append('%s King Captured!' % self.player_str(who))
        self.messages.append('%s wins!' % self.player_str(winner))
        self.update_label()

    def act(self):
        if not self.peers and not env.dev_mode:
            return
        if self.game_model.counter < latency:
            self.game_model.counter += 1
            return
        if len(self.iter_actions.get(self.game_model.counter, {})) <= len(self.peers):
            # We haven't got communications from all peers for this iteration.
            # So we'll wait.
            return
        all_actions = sorted(self.iter_actions[self.game_model.counter].items())
        if self.is_replay:
            all_actions += sorted(self.iter_actions[self.replay_counter].items())
            self.replay_counter += 1
        for i, actions in all_actions:
            for action_type, params in actions:
                action_func = getattr(self, 'action_'+action_type, None)
                if action_func is None:
                    self.messages.append(action_type + ': no such action')
                else:
                    if not hasattr(action_func, 'quiet'):
                        self.messages.append(self.nick(i) + ' did ' + action_type.upper())
                    if env.dev_mode:
                        action_func(i, *params)
                    else:
                        try:
                            action_func(i, *params)
                        except:
                            self.messages.append('action ' + action_type + ' failed')
        self.update_label()
        self.game_model.counter += 1

    def on_clock(self, _interval):
        self.communicate()

        if self.instance_id not in self.iter_actions.setdefault(self.game_model.counter+latency, {}):
            self.iter_actions[self.game_model.counter+latency][self.instance_id] = self.game_model.cur_actions
            self.game_model.cur_actions = []

        self.act()

        self.board_view.update_dst()
        self.board_view.show_board()

class Chess2App(App):
    def build(self):
        self.game = Game()
        self.game.text_input.focus = True
        return self.game
    def stop(self):
        self.game.done = True

if __name__ == '__main__':
    Window.softinput_mode = 'pan'
    Chess2App().run()
