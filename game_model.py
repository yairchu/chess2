import chess
import env

class GameModel:
    player_freeze_time = 0 if env.dev_mode else 20

    def __init__(self):
        self.player = 0
        self.mode = None
        self.board = {}
        self.board_size = [4, 4]
        self.num_boards = 1
        self.messages = []
        self.on_message = []
        self.on_init = []
        self.reset()

    def reset(self):
        self.counter = 0
        self.cur_actions = []

    def add_message(self, msg):
        self.messages.append(msg)
        for x in self.on_message:
            x()

    def active(self):
        return self.mode in ['tutorial', 'play']

    def init(self, num_boards=None):
        '''
        Initialize game.
        Can initialize with more game boards for more players!
        '''

        if num_boards is not None:
            self.num_boards = num_boards
        self.reset()
        self.player_freeze = {}
        self.board = {}
        self.board_size = [8*self.num_boards, 8]
        self.num_players = self.num_boards * 2
        for who, (x, y0, y1) in enumerate([(0, 0, 1), (0, 7, 6), (8, 0, 1), (8, 7, 6)][:self.num_players]):
            for dx, piece in enumerate(chess.first_row):
                p = piece(who, (x+dx, y0), self)
                if piece == chess.King:
                    p.on_die = lambda who=who: self.king_captured(who)
                chess.Pawn(who, (x+dx, y1), self)
        for x in self.on_init:
            x()

    def in_bounds(self, pos):
        for x, s in zip(pos, self.board_size):
            if not (0 <= x < s):
                return False
        return True

    def add_action(self, act_type, *params):
        'Queue an action to be executed'
        self.cur_actions.append((act_type, params))

    def action_msg(self, nick, *txt):
        self.add_message('%s: %s' % (nick, ' '.join(txt)))
    action_msg.quiet = True

    def action_move(self, _nick, src, dst):
        if src not in self.board:
            return
        piece = self.board[src]
        if piece.move(dst):
            self.add_message('%s %s moved' % (self.player_str(piece.player), type(piece).__name__.lower()))
            if self.mode == 'tutorial' and self.tutorial_messages:
                self.add_message('')
                self.add_message(self.tutorial_messages.pop(0))
    action_move.quiet = True

    def action_reset(self, _nick, num_boards=None):
        self.init(None if num_boards is None else int(num_boards))

    def player_str(self, player):
        if player is None:
            return 'spectator'
        r = ['White', 'Black'][player%2]
        if self.num_boards > 1:
            r += '#'+str(player//2)
        return r

    def action_become(self, nick, player):
        player = int(player)
        self.add_message(nick + ' becomes ' + self.player_str(player))
        if nick == 'You':
            self.player = player
            for x in self.on_init:
                x()
    action_become.quiet = True

    def action_credits(self, _nick):
        self.add_message('''
            Programming: Yair Chuchem
            Chess sets/Graphics: Armondo H. Marroquin and Eric Bentzen (http://www.enpassant.dk/chess/fonteng.htm)
            Logic/Concept: Ancient People, Yair Chuchem, and fellow Play-Testers
            Programming Infrastructure: Python (Guido van Rossum and friends), Pygame/SDL (Pete Shinners and friends)
            ''')
