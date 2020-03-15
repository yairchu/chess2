'''
A networked real-time strategy game based on Chess
'''

import itertools
from itertools import count

import marshal
import operator
import random
import select
import socket
import sys

import pygame

pygame.init()
S = 45
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
font = pygame.font.SysFont(pygame.font.get_default_font(), fontsize)

text_pos = (0, 600-fontsize)
num_msg_lines = 6

class Piece:
    freeze_time = 80
    last_move_time = 0
    last_pos = (3.5, 3.5)
    def __init__(self, player, pos, game):
        self.player = player
        self.pos = pos
        self.freeze_until = 0
        self.game = game
        self.board = game.board
        game.board[pos] = self
    def image(self, transparent=False):
        return self._images[self.game.chess_sets_perm[self.player]][transparent]
    def side(self):
        return self.player % 2
    def die(self):
        if self.board[self.pos] == self:
            del self.board[self.pos]
        self._die()
    def _die(self):
        pass
    def move(self, pos):
        if self.board[self.pos] is not self or pos not in self.moves():
            return False
        del self.board[self.pos]
        self.last_pos = self.pos
        self.last_move_time = self.game.counter
        self.pos = pos
        if pos in self.board:
            self.board[pos].die()
        self.board[self.pos] = self
        self.freeze_until = self.game.counter+self.freeze_time
        self.game.player_freeze[self.player] = self.game.counter+self.game.player_freeze_time
        return True
    def moves(self, with_freeze=True):
        if with_freeze and self.game.counter < max(
                self.freeze_until, self.game.player_freeze.get(self.player, 0)):
            return
        for streak in self._moves(*self.pos):
            for dst in streak:
                if dst in self.board and self.board[dst].side() == self.side():
                    break
                if self.game.in_bounds(dst):
                    yield dst
                else:
                    break
                if dst in self.board:
                    break
    def sight(self):
        return self.moves(with_freeze=False)

class Rook(Piece):
    sight_color = (0.5, 0.5, 1)
    @staticmethod
    def _moves(x, y):
        yield ((x+d, y) for d in count(1))
        yield ((x-d, y) for d in count(1))
        yield ((x, y+d) for d in count(1))
        yield ((x, y-d) for d in count(1))

class Bishop(Piece):
    sight_color = (0, 0, 1)
    @staticmethod
    def _moves(x, y):
        yield ((x+d, y+d) for d in count(1))
        yield ((x-d, y-d) for d in count(1))
        yield ((x+d, y-d) for d in count(1))
        yield ((x-d, y+d) for d in count(1))

class Queen(Rook, Bishop):
    sight_color = (1, 0, 0)
    @staticmethod
    def _moves(x, y):
        return itertools.chain(Rook._moves(x, y), Bishop._moves(x, y))

class Knight(Piece):
    sight_color = (0, 1, 0)
    @staticmethod
    def _moves(x, y):
        for a in [-1, 1]:
            for b in [-2, 2]:
                yield [(x+a, y+b)]
                yield [(x+b, y+a)]

class King(Piece):
    sight_color = (0, 1, 1)
    freeze_time = 60
    def sight(self):
        for pos in self.moves(False):
            yield pos
        for streak in itertools.chain(Knight._moves(*self.pos), Queen._moves(*self.pos)):
            for pos in streak:
                if not self.game.in_bounds(pos):
                    break
                if pos in self.board:
                    if self.pos in self.board[pos].moves(False):
                        yield pos
                    break
    def _moves(self, x, y):
        for a in range(x-1, x+2):
            for b in range(y-1, y+2):
                if (a, b) != (x, y):
                    yield [(a, b)]
    def _die(self):
        for piece in list(self.board.values()):
            if piece is not self and piece.player == self.player:
                piece.die()

class Pawn(Piece):
    sight_color = (0.5, 0.5, 0.5)
    egg_time = 60
    def move(self, pos):
        if not super(Pawn, self).move(pos):
            return False
        if (self.side() == 0 and pos[1] == 7) or (self.side() == 1 and pos[1] == 0):
            self.die()
            new_piece = Queen(self.player, pos, self.game)
            new_piece.freeze_until = self.game.counter+self.egg_time
        return True
    def sight(self):
        for pos in super(Pawn, self).sight():
            yield pos
        delta = -1 if self.side() else 1
        x, y = self.pos
        for a in [x-1, x+1]:
            if self.game.in_bounds((a, y+delta)):
                yield a, y+delta
    def _moves(self, x, y):
        start_row, delta = (6, -1) if self.side() else (1, 1)
        m = [(x, y+delta)]
        if y == start_row:
            m.append((x, y+2*delta))
        for c, p in enumerate(m):
            if p in self.board:
                m = m[:c]
                break
        yield m
        for a in [x-1, x+1]:
            if (a, y+delta) in self.board:
                yield [(a, y+delta)]

def run(func):
    return func()

@run
def init_piece_images():
    pieces_image = pygame.image.load('chess.png')
    transparent_pieces_image = pygame.image.load('chess.png')
    for x in range(S*6):
        for y in range(S*6):
            r, g, b, a = transparent_pieces_image.get_at((x, y))
            transparent_pieces_image.set_at((x, y), (r, g, b, a//2))
    for x, piece in enumerate([King, Queen, Rook, Bishop, Knight, Pawn]):
        piece._images = [[image.subsurface([S*x, S*y, S, S])
                          for image in [pieces_image, transparent_pieces_image]] for y in range(6)]

@run
def init_piece_move_prefernce():
    for preference, piece in enumerate([King, Pawn, Knight, Bishop, Rook, Queen]):
        piece.move_preference = preference


gameport = 33333

def poll(sock):
    return select.select([sock], [], [], 0)[0] != []


latency = 5

def quiet_action(func):
    func.quiet = True
    return func

def c_ceil_div(x, d):
    r = (abs(x)+d-1)//d
    return -r if x < 0 else r

class Game:
    player_freeze_time = 20

    def __init__(self):
        self.id = random.randrange(2**64)
        self.nicknames = {}
        self.entry = ''
        self.messages = []
        self.counter = 0
        self.cur_actions = []
        self.iter_actions = {}
        self.peers = []
        self.mouse_pos = None
        self.connecting = False
        self.init_socket()
        self.action_reset(self.id)
        self.action_help(self.id)
        self.last_start = None
        self.last_selected_at_dst = {}
        self.is_replay = False
        self.player_freeze = {}
        try:
            self.socket.bind(('', gameport))
        except socket.error:
            self.init_socket()
            self.add_action('connect', 'localhost')

    def init_board(self, num_boards=1):
        self.num_boards = int(num_boards)
        self.board = {}
        self.board_size = [8*num_boards, 8]
        self.num_players = num_boards * 2
        for who, (x, y0, y1) in enumerate([(0, 0, 1), (0, 7, 6), (8, 0, 1), (8, 7, 6)][:self.num_players]):
            for dx, piece in enumerate(
                    [Rook, Knight, Bishop, King, Queen, Bishop, Knight, Rook]):
                piece(who, (x+dx, y0), self)
                Pawn(who, (x+dx, y1), self)
        self.board_pos = (resolution[0]-S*8*num_boards)//2, (resolution[1]-S*8)//2
        self.shuffle_sets()

    def shuffle_sets(self):
        a = [0, 2, 4]
        b = [1, 3, 5]
        random.shuffle(a)
        random.shuffle(b)
        self.chess_sets_perm = [[a, b][i%2][i//2] for i in range(6)]

    def init_socket(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def add_action(self, act_type, *params):
        self.cur_actions.append((act_type, params))

    def in_bounds(self, pos):
        return 0 <= pos[0] < self.board_size[0] and 0 <= pos[1] < self.board_size[1]

    def nick(self, i):
        return self.nicknames.get(i, 'anonymouse')

    event_handlers = []

    @event_handlers.append
    def KEYDOWN(self, event):
        if event.key in self.event_handlers:
            self.event_handlers[event.key](self)
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
        if self.entry[:1] == '/':
            self.add_action(*self.entry[1:].split())
        else:
            self.add_action('msg', self.entry)
        self.entry = ''

    @event_handlers.append
    def K_ESCAPE(self):
        sys.exit()

    @event_handlers.append
    def K_F1(self):
        toggle_fullscreen()

    @event_handlers.append
    def K_F2(self):
        if self.started or self.is_replay:
            self.messages.append('Cannot change player after start!')
            return
        if self.player is None:
            player = 0
        else:
            player = self.player+1
        if player == self.num_players:
            player = None
        self.add_action('become', player)

    @event_handlers.append
    def K_F3(self):
        self.add_action('reset', 1)

    @event_handlers.append
    def K_F4(self):
        self.add_action('reset', 2)

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
        if not self.started and not self.is_replay and [] != self.peers:
            if len(set(x for x in list(self.who_is_who.values()) if x is not None)) == self.num_players:
                self.started = True
                self.last_start = self.counter
            else:
                self.messages.append('CANNOT START WITH ORPHANED ARMIES')
            return
        if src in self.board:
            self.board[src].move(dst)

    @quiet_action
    def action_connect(self, _id, host):
        self.socket.sendto(marshal.dumps((self.id, 'HELLO')), 0, (host, gameport))
        self.connecting = True

    @quiet_action
    def action_welcome(self, i, peer, peer_id):
        self.action_reset(i)
        if peer_id == self.id or peer in self.peers:
            return
        self.peers.append(peer)
        self.messages.append('connecting to %s' % (peer, ))
        self.add_action('nick', self.nick(self.id))

    def action_reset(self, _id, num_boards=1):
        self.init_board(int(num_boards))
        self.player = None
        self.started = False
        self.who_is_who = {}
        self.potential_pieces = []
        self.selected = None
        self.is_dragging = False

    def action_forcestart(self, _id):
        self.started = True
        self.last_start = self.counter

    def action_replay(self, i):
        if self.last_start is None:
            self.messages.append('NO GAME WAS PLAYED')
            return
        self.iter_actions[self.counter][i] = [('endreplay', ())]
        self.replay_counter = self.last_start
        self.action_reset(i, self.num_boards)
        self.is_replay = True

    def action_endreplay(self, _id):
        self.is_replay = False

    @quiet_action
    def action_become(self, i, player):
        if i == self.id:
            self.player = player
        self.who_is_who[i] = player
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
        self.messages.extend('''Welcome to - Chess II: King Dugan's Revenge.
        commands: /help | /connect <host> | /reset [num-boards] | /nick <nickname> | /replay | /credits
        keys: F1=toggle-fullscreen | F2=choose-set | F3 = reset | F4 = 4-players
        '''.split('\n'))

    def show_board(self):
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

        display.fill((0, 0, 0))
        cols = {}
        for pos in see:
            cols[pos] = (240, 240, 240)
        for pos, col in movesee.items():
            cols[pos] = [128+a*127./max(col) for a in col]
        for pos, col in flash.items():
            cols[pos] = [255*x for x in col]

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
        display.blit(font.render('> '+self.entry, 255, (255, 255, 255)), text_pos)
        for y, msg in enumerate(self.messages[-num_msg_lines:]):
            display.blit(font.render(msg, 255, (255, 255, 255)), (0, fontsize*y))
        pygame.display.flip()

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
        packet = marshal.dumps((self.id,
                                [(i, self.iter_actions.setdefault(i, {}).setdefault(self.id, []))
                                 for i in range(max(0, self.counter-latency), self.counter+latency)]))
        was_connecting = self.connecting
        for peer in self.peers:
            self.socket.sendto(packet, 0, peer)
        while poll(self.socket):
            packet, peer = self.socket.recvfrom(0x1000)
            peer_id, peer_iter_actions = marshal.loads(packet)
            if peer_iter_actions == 'HELLO':
                self.add_action('welcome', peer, peer_id)
                continue
            for i, actions in peer_iter_actions:
                self.iter_actions.setdefault(i, {})[peer_id] = actions
                if self.connecting:
                    for action_type, _params in actions:
                        if action_type == 'welcome':
                            self.connecting = False
                            self.counter = i
                            self.peers.append(peer)
                            self.messages.append('connection successful')
        if was_connecting and not self.connecting:
            self.iter_actions = {}

    def act(self):
        if self.counter < latency:
            self.counter += 1
            return
        if len(self.iter_actions.get(self.counter, {})) <= len(self.peers):
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

        if self.id not in self.iter_actions.setdefault(self.counter+latency, {}):
            self.iter_actions[self.counter+latency][self.id] = self.cur_actions
            self.cur_actions = []

        self.act()

        pygame.event.pump()
        for event in pygame.event.get():
            if event.type in self.event_handlers:
                self.event_handlers[event.type](self, event)

        self.update_dst()
        self.show_board()


game = Game()
while True:
    game.iteration()
    clock.tick(30)
