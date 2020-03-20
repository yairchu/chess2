'''
A networked real-time strategy game based on Chess
'''

import itertools
import marshal
import operator
import os
import random
import select
import socket
import time
import threading
import urllib.request

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
import stun

import chess

num_msg_lines = 6

def poll(sock):
    return select.select([sock], [], [], 0)[0] != []


latency = 5

def quiet_action(func):
    func.quiet = True
    return func

def centered_text(text, pos_top_y):
    t = font.render(text, 255, (255, 255, 255))
    display.blit(t, ((resolution[0] - t.get_width())//2, pos_top_y))

class Game(BoxLayout):
    player_freeze_time = 20

    def __init__(self, dev_mode=False, **kwargs):
        super(Game, self).__init__(**kwargs)
        self.done = False
        self.instance_id = random.randrange(2**64)
        self.nicknames = {}
        self.address = None
        self.messages = []
        self.counter = 0
        self.last_start = 0
        self.cur_actions = []
        self.iter_actions = {}
        self.peers = []
        self.action_reset(self.instance_id)
        self.last_selected_at_dst = {}
        self.is_replay = False
        self.player = 0
        self.player_freeze = {}
        self.dev_mode = dev_mode
        self.socket = None
        self.threads = []
        net_thread = threading.Thread(target=self.net_thread_go)
        self.threads.append(net_thread)
        if not dev_mode:
            net_thread.start()

        self.board_view = BoardView(self)
        self.add_widget(self.board_view)

        self.info_pane = BoxLayout(orientation='vertical')
        self.add_widget(self.info_pane)

        self.label = Label(halign='center', valign='bottom')
        def update_label_text_size(*args):
            self.label.text_size = (self.label.width, None)
        self.label.bind(width=update_label_text_size)
        self.info_pane.add_widget(self.label)

        self.text_input = TextInput(
            multiline=False,
            text_validate_unfocus=False,
            size_hint=(1, 0),
            size_hint_min_y=60)
        def steal_focus(*args):
            if not self.text_input.focus:
                self.text_input.focus = True
        self.text_input.bind(
            on_text_validate=self.handle_text_input,
            focus=steal_focus)
        self.info_pane.add_widget(self.text_input)

        self.messages.append('')
        self.messages.append('Welcome to Chess 2!')
        self.messages.append('Developer Mode' if dev_mode else 'Establishing server connection...')
        self.update_label()

        self.bind(size=self.resized)
        Clock.schedule_interval(self.on_clock, 1/30)

    def update_label(self):
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
            self.messages.clear()
            self.messages.append('')
            self.messages.append('Connection successful!')
            self.messages.append('THE GAME BEGINS!')
            self.update_label()

    def init_board(self, num_boards=1):
        '''
        Initialize game.
        Can initialize with more game boards for more players!
        '''

        self.num_boards = int(num_boards)
        self.board = {}
        self.board_size = [8*num_boards, 8]
        self.num_players = num_boards * 2
        for who, (x, y0, y1) in enumerate([(0, 0, 1), (0, 7, 6), (8, 0, 1), (8, 7, 6)][:self.num_players]):
            for dx, piece in enumerate(chess.first_row):
                piece(who, (x+dx, y0), self)
                chess.Pawn(who, (x+dx, y1), self)
        self.shuffle_sets()

    def shuffle_sets(self):
        'Randomly change which chess piece images sets are used'
        a = [0, 2, 4]
        b = [1, 3, 5]
        random.shuffle(a)
        random.shuffle(b)
        self.chess_sets_perm = [[a, b][i%2][i//2] for i in range(6)]

    def add_action(self, act_type, *params):
        'Queue an action to be executed'
        self.cur_actions.append((act_type, params))

    def in_bounds(self, pos):
        for x, s in zip(pos, self.board_size):
            if not (0 <= x < s):
                return False
        return True

    def nick(self, i):
        return self.nicknames.get(i, 'anonymouse')

    def handle_text_input(self, entry):
        command = entry.text
        entry.text = ''
        if not command:
            return
        if command[:1] == '/':
            self.add_action(*command[1:].split())
            return
        if self.peers:
            # Chat
            self.add_action('msg', command)
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
        self.player = 1

    def K_F3(self):
        self.add_action('reset', 1)

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
        if src not in self.board:
            return
        self.board[src].move(dst)

    def action_reset(self, _id, num_boards=1):
        self.init_board(int(num_boards))
        self.player = None
        self.potential_pieces = []
        self.last_start = self.counter

    def action_replay(self, i):
        self.iter_actions[self.counter][i] = [('endreplay', ())]
        self.replay_counter = self.last_start
        self.action_reset(i, self.num_boards)
        self.is_replay = True

    def action_endreplay(self, _id):
        self.is_replay = False

    @quiet_action
    def action_become(self, i, player):
        player = int(player)
        if i == self.instance_id:
            self.player = player
        if player is None:
            player_str = 'spectator'
        else:
            player_str = ['White', 'Black'][player%2]+'#'+str(player//2)
        self.messages.append(self.nick(i) + ' becomes ' + player_str)

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
                for i in range(max(0, self.counter-latency), self.counter+latency)]))
        for peer in self.peers:
            self.socket.sendto(packet, 0, peer)
        while poll(self.socket):
            packet, peer = self.socket.recvfrom(0x1000)
            peer_id, peer_iter_actions = marshal.loads(packet)
            for i, actions in peer_iter_actions:
                self.iter_actions.setdefault(i, {})[peer_id] = actions

    def act(self):
        if not self.peers and not self.dev_mode:
            return
        if self.counter < latency:
            self.counter += 1
            return
        if len(self.iter_actions.get(self.counter, {})) <= len(self.peers):
            # We haven't got communications from all peers for this iteration.
            # So we'll wait.
            return
        all_actions = sorted(self.iter_actions[self.counter].items())
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
                    try:
                        action_func(i, *params)
                    except:
                        self.messages.append('action ' + action_type + ' failed')
        self.update_label()
        self.counter += 1

    def on_clock(self, _interval):
        self.communicate()

        if self.instance_id not in self.iter_actions.setdefault(self.counter+latency, {}):
            self.iter_actions[self.counter+latency][self.instance_id] = self.cur_actions
            self.cur_actions = []

        self.act()

        self.board_view.update_dst()
        self.board_view.show_board()

class BoardView(Widget):
    def __init__(self, game, **kwargs):
        super(BoardView, self).__init__(**kwargs)
        self.game = game
        Window.bind(mouse_pos=self.mouse_motion)
        self.bind(size=self.resized)
        self.mouse_pos = None
        self.reset()

    def resized(self, a, b):
        self.square_size = min(self.size) / 8

    def reset(self):
        self.selected = None
        self.is_dragging = False

    def show_board(self):
        cols, see = self.board_info()

        self.canvas.clear()
        sq = (self.square_size-1, self.square_size-1)
        with self.canvas:
            for (x, y), col in cols.items():
                sx, sy = self.screen_pos((x, y))
                Color(*[x/255 for x in col])
                if (x, y) in self.game.board and self.game.board[x, y].freeze_until > self.game.counter:
                    Rectangle(pos=(sx+3, sy+3), size=(self.square_size-7, self.square_size-7))
                else:
                    Rectangle(pos=(sx, sy), size=sq)

            for pos, piece in self.game.board.items():
                if pos not in see:
                    continue
                transparent = False
                move_time = (self.game.counter - piece.last_move_time)*0.1
                if move_time < 1:
                    pos_between = move_time
                    if piece.last_pos is not None:
                        last_screen_pos = self.screen_pos(piece.last_pos)
                        new_screen_pos = self.screen_pos(pos)
                        Rectangle(
                            texture=piece.image(),
                            pos=[int(last_screen_pos[i]+(new_screen_pos[i]-last_screen_pos[i])*pos_between) for i in range(2)],
                            size=sq)
                if piece is self.selected:
                    transparent = True
                Color(1, 1, 1, .5 if transparent else 1)
                Rectangle(texture=piece.image(), pos=self.screen_pos(pos), size=sq)

            if self.selected is not None and self.dst_pos is not None:
                Color(1, 1, 1, .5)
                Rectangle(
                    texture=self.selected.image(),
                    pos=self.screen_pos(self.dst_pos),
                    size=sq)

            if self.is_dragging:
                x, y = self.raw_mouse_pos
                Color(1, 1, 1, .5)
                Rectangle(
                    texture=self.selected.image(),
                    pos=(x-self.square_size//2, y-self.square_size//2),
                    size=sq)

    def board_info(self):
        flash = {}
        flashy = self.game.board.get(self.mouse_pos)
        if flashy is not None and flashy.player == self.game.player:
            for pos in flashy.moves():
                flash[pos] = flashy.sight_color

        movesee = {}
        see = set()
        for piece in self.game.board.values():
            if self.game.player is not None and piece.side() != self.game.player%2:
                continue
            see.add(piece.pos)
            if piece.player == self.game.player:
                moves = set(piece.moves())
                if self.mouse_pos in moves:
                    flash[piece.pos] = piece.sight_color
                else:
                    movesee[piece.pos] = piece.sight_color
            for dst in itertools.chain(piece.sight()):
                see.add(dst)
                if piece.player == self.game.player and dst in moves:
                    movesee[dst] = list(map(operator.add, movesee.get(dst, [0]*3), piece.sight_color))

        cols = {}
        for pos in see:
            cols[pos] = (240, 240, 240)
        for pos, col in movesee.items():
            cols[pos] = [128+a*127./max(col) for a in col]
        for pos, col in flash.items():
            cols[pos] = [255*x for x in col]

        return cols, see

    def on_touch_down(self, event):
        self.calc_mouse_pos(event.pos)
        if event.is_mouse_scrolling:
            if [] == self.potential_pieces:
                return
            d = 1 if event.button == 'scrolldown' else -1
            self.selected = self.potential_pieces[
                (self.potential_pieces.index(self.selected)+d)%len(self.potential_pieces)]
            return
        if self.mouse_pos in self.game.board and self.game.board[self.mouse_pos].player == self.game.player:
            self.is_dragging = True
            self.selected = self.game.board[self.mouse_pos]
            self.dst_pos = None

    def mouse_motion(self, _win, pos):
        self.raw_mouse_pos = pos
        self.calc_mouse_pos(pos)

    def on_touch_up(self, event):
        if event.is_mouse_scrolling:
            return
        self.calc_mouse_pos(event.pos)
        self.is_dragging = False
        if self.selected is None or self.dst_pos is None:
            return
        if not self.game.peers and not self.game.dev_mode:
            return
        self.game.add_action('move', self.selected.pos, self.dst_pos)
        self.selected = None

    def calc_mouse_pos(self, pos):
        x, y = pos
        self.mouse_pos = (x-self.pos[0])//self.square_size, (y-self.pos[1])//self.square_size

    def screen_pos(self, pos):
        return self.pos[0]+self.square_size*pos[0], self.pos[1]+self.square_size*pos[1]

    last_pos = None
    def update_dst(self):
        if self.selected is not None and self.game.board.get(self.selected.pos) is not self.selected:
            self.selected = None
        if self.is_dragging and self.selected is not None:
            self.dst_pos = None
            if self.mouse_pos in self.selected.moves():
                self.dst_pos = self.mouse_pos
            return
        self.is_dragging = False
        self.potential_pieces = []
        for piece in self.game.board.values():
            if piece.player == self.game.player and self.mouse_pos in piece.moves():
                self.potential_pieces.append(piece)
        self.potential_pieces.sort(key = lambda x: x.move_preference)
        if [] == self.potential_pieces:
            self.selected = None
        else:
            self.dst_pos = self.mouse_pos
            if self.last_pos != self.dst_pos or self.selected not in self.potential_pieces:
                self.selected = self.potential_pieces[0]
            self.last_pos = self.dst_pos

class Chess2App(App):
    def build(self):
        self.game = Game()
        self.game.text_input.focus = True
        return self.game
    def stop(self):
        self.game.done = True

if __name__ == '__main__':
    Chess2App().run()
