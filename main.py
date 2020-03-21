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
import sys
import time
import threading
import urllib.request

import pygame
import stun

import chess

pygame.init()
S = chess.S
resolution = 800, 600

display = pygame.display.set_mode(resolution, 0)

is_fullscreen = False

def toggle_fullscreen():
    global is_fullscreen, display
    is_fullscreen = not is_fullscreen
    pygame.display.quit()
    if is_fullscreen:
        flags = pygame.FULLSCREEN
    else:
        flags = 0
    display = pygame.display.set_mode(resolution, flags)


clock = pygame.time.Clock()
fontsize = 20
font = pygame.font.SysFont('Sans', fontsize-3)

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

class Game:
    player_freeze_time = 20

    def __init__(self, dev_mode=False):
        self.done = False
        self.instance_id = random.randrange(2**64)
        self.nicknames = {}
        self.address = None
        self.entry = ''
        self.messages = []
        self.counter = 0
        self.last_start = 0
        self.cur_actions = []
        self.iter_actions = {}
        self.peers = []
        self.mouse_pos = None
        self.action_reset(self.instance_id)
        self.last_selected_at_dst = {}
        self.is_replay = False
        self.player = 0
        self.player_freeze = {}
        self.messages.append('')
        self.messages.append('Welcome to Chess 2!')
        self.messages.append('Developer Mode' if dev_mode else 'Establishing server connection...')
        self.dev_mode = dev_mode
        self.socket = None
        self.threads = []
        net_thread = threading.Thread(target=self.net_thread_go)
        self.threads.append(net_thread)
        if not dev_mode:
            net_thread.start()

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
        self.board_pos = (resolution[0]-S*8*num_boards)//2, (resolution[1]-S*8)//2
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

    event_handlers = []

    @event_handlers.append
    def KEYDOWN(self, event):
        if event.key in self.event_handlers:
            self.event_handlers[event.key](self)
        elif event.key == pygame.K_q and (event.mod & pygame.KMOD_META) != 0:
            # Cmd+Q (to quit on macs, todo: other platforms?)
            self.done = True
        elif 32 <= event.key < 128:
            self.entry += chr(event.key)

    @event_handlers.append
    def K_BACKSPACE(self):
        self.entry = self.entry[:-1]

    @event_handlers.append
    def K_DELETE(self):
        self.entry = ''

    @event_handlers.append
    def K_RETURN(self):
        if not self.entry:
            return
        command = self.entry
        self.entry = ''
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

    @event_handlers.append
    def K_ESCAPE(self):
        self.done = True

    @event_handlers.append
    def QUIT(self, _event):
        self.done = True

    @event_handlers.append
    def K_F3(self):
        self.add_action('reset', 1)

    @event_handlers.append
    def MOUSEBUTTONDOWN(self, event):
        self.calc_mouse_pos(event)
        if event.button == 1:
            if self.mouse_pos in self.board and self.board[self.mouse_pos].player == self.player:
                self.is_dragging = True
                self.selected = self.board[self.mouse_pos]
            return
        if [] == self.potential_pieces:
            return
        d = 1
        if event.button == 4:
            d = -1
        self.selected = self.potential_pieces[
            (self.potential_pieces.index(self.selected)+d)%len(self.potential_pieces)]

    @event_handlers.append
    def MOUSEMOTION(self, event):
        self.calc_mouse_pos(event)

    @event_handlers.append
    def MOUSEBUTTONUP(self, event):
        self.calc_mouse_pos(event)
        self.is_dragging = False
        if event.button != 1 or self.selected is None or self.dst_pos is None:
            return
        if not self.peers and not self.dev_mode:
            return
        self.add_action('move', self.selected.pos, self.dst_pos)
        self.selected = None

    event_handlers = dict((getattr(pygame, func.__name__), func) for func in event_handlers)

    def calc_mouse_pos(self, event):
        x, y = event.pos
        self.mouse_pos = (x-self.board_pos[0])//S, (y-self.board_pos[1])//S

    def screen_pos(self, pos):
        return self.board_pos[0]+S*pos[0], self.board_pos[1]+S*pos[1]

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
        self.selected = None
        self.is_dragging = False
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

    last_pos = None
    def update_dst(self):
        if self.selected is not None and self.board.get(self.selected.pos) is not self.selected:
            self.selected = None
        if self.is_dragging and self.selected is not None:
            self.dst_pos = None
            if self.mouse_pos in self.selected.moves():
                self.dst_pos = self.mouse_pos
            return
        self.is_dragging = False
        self.potential_pieces = []
        for piece in self.board.values():
            if piece.player == self.player and self.mouse_pos in piece.moves():
                self.potential_pieces.append(piece)
        self.potential_pieces.sort(key = lambda x: x.move_preference)
        if [] == self.potential_pieces:
            self.selected = None
        else:
            self.dst_pos = self.mouse_pos
            if self.last_pos != self.dst_pos or self.selected not in self.potential_pieces:
                self.selected = self.potential_pieces[0]
            self.last_pos = self.dst_pos

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
        self.counter += 1

    def iteration(self):
        self.communicate()

        if self.instance_id not in self.iter_actions.setdefault(self.counter+latency, {}):
            self.iter_actions[self.counter+latency][self.instance_id] = self.cur_actions
            self.cur_actions = []

        self.act()

        pygame.event.pump()
        for event in pygame.event.get():
            if event.type in self.event_handlers:
                self.event_handlers[event.type](self, event)

        self.update_dst()
        self.show_board()

    def show_board(self):
        display.fill((0, 0, 0))

        cols, see = self.board_info()

        for (x, y), col in cols.items():
            sx, sy = self.screen_pos((x, y))
            if (x, y) in self.board and self.board[x, y].freeze_until > self.counter:
                display.subsurface([sx+3, sy+3, S-7, S-7]).fill(col)
            else:
                display.subsurface([sx, sy, S-1, S-1]).fill(col)

        for pos, piece in self.board.items():
            if pos not in see:
                continue
            transparent = False
            move_time = (self.counter - piece.last_move_time)*0.1
            if move_time < 1:
                pos_between = move_time
                if piece.last_pos is not None:
                    last_screen_pos = self.screen_pos(piece.last_pos)
                    new_screen_pos = self.screen_pos(pos)
                    display.blit(piece.image(True),
                                [int(last_screen_pos[i]+(new_screen_pos[i]-last_screen_pos[i])*pos_between) for i in range(2)])
            if piece is self.selected:
                transparent = True
            display.blit(piece.image(transparent), self.screen_pos(pos))

        if self.selected is not None and self.dst_pos is not None:
            display.blit(self.selected.image(transparent = True), self.screen_pos(self.dst_pos))

        if self.is_dragging:
            x, y = pygame.mouse.get_pos()
            display.blit(self.selected.image(transparent = True), (x-S//2, y-S//2))

        (_, board_bottom) = self.screen_pos((0,8))
        centered_text(
            '> '+self.entry,
            board_bottom + (resolution[1]-board_bottom-fontsize) // 2)
        for y, msg in enumerate(self.messages[-num_msg_lines:]):
            centered_text(msg, fontsize*y)

        pygame.display.flip()

    def board_info(self):
        flash = {}
        flashy = self.board.get(self.mouse_pos)
        if flashy is not None and flashy.player == self.player:
            for pos in flashy.moves():
                flash[pos] = flashy.sight_color

        movesee = {}
        see = set()
        for piece in self.board.values():
            if self.player is not None and piece.side() != self.player%2:
                continue
            see.add(piece.pos)
            if piece.player == self.player:
                moves = set(piece.moves())
                if self.mouse_pos in moves:
                    flash[piece.pos] = piece.sight_color
                else:
                    movesee[piece.pos] = piece.sight_color
            for dst in itertools.chain(piece.sight()):
                see.add(dst)
                if piece.player == self.player and dst in moves:
                    movesee[dst] = list(map(operator.add, movesee.get(dst, [0]*3), piece.sight_color))

        cols = {}
        for pos in see:
            cols[pos] = (240, 240, 240)
        for pos, col in movesee.items():
            cols[pos] = [128+a*127./max(col) for a in col]
        for pos, col in flash.items():
            cols[pos] = [255*x for x in col]

        return cols, see

game = Game('--dev' in sys.argv)
while not game.done:
    game.iteration()
    clock.tick(30)
