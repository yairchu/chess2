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
