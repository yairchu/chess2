import chess
import env

class GameModel:
    player_freeze_time = 0 if env.dev_mode else 20

    def __init__(self):
        self.player = 0
        self.mode = None
        self.board = {}
        self.board_size = [4, 4]
        self.reset()

    def reset(self):
        self.counter = 0
        self.cur_actions = []

    def active(self):
        return self.mode in ['tutorial', 'play']

    def init(self, num_boards=1):
        '''
        Initialize game.
        Can initialize with more game boards for more players!
        '''

        self.reset()
        self.player_freeze = {}
        self.num_boards = int(num_boards)
        self.board = {}
        self.board_size = [8*num_boards, 8]
        self.num_players = num_boards * 2
        for who, (x, y0, y1) in enumerate([(0, 0, 1), (0, 7, 6), (8, 0, 1), (8, 7, 6)][:self.num_players]):
            for dx, piece in enumerate(chess.first_row):
                p = piece(who, (x+dx, y0), self)
                if piece == chess.King:
                    p.on_die = lambda who=who: self.king_captured(who)
                chess.Pawn(who, (x+dx, y1), self)

    def in_bounds(self, pos):
        for x, s in zip(pos, self.board_size):
            if not (0 <= x < s):
                return False
        return True

    def add_action(self, act_type, *params):
        'Queue an action to be executed'
        self.cur_actions.append((act_type, params))
