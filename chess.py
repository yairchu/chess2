import itertools
from itertools import count

from kivy.uix.image import Image

class Piece:
    freeze_time = 80
    last_move_time = 0

    last_pos = None

    def __init__(self, player, pos, game):
        self.player = player
        self.pos = pos
        self.freeze_until = 0
        self.game = game
        self.board = game.board
        game.board[pos] = self

    def image(self, chess_sets_perm):
        'Get image for piece'
        return self._images[chess_sets_perm[self.player]]

    def side(self):
        return self.player % 2

    def die(self):
        if self.board[self.pos] == self:
            del self.board[self.pos]
        self.on_die()

    def on_die(self):
        'Callback for actions on piece dying (overridden for King)'
        pass

    def move(self, pos):
        if self.board[self.pos] is not self or pos not in self.moves():
            # Situation changed since move queued, can't perform this move!
            return False
        assert isinstance(pos[0], int)
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

    def moves(self):
        if self.game.counter < max(
                self.freeze_until, self.game.player_freeze.get(self.player, 0)):
            return
        yield from self.base_moves()

    def sight(self):
        'What squares can this piece see (overridden for Pawn)'
        yield from self.base_moves()

    def base_moves(self):
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
        yield from self.base_moves()
        for streak in itertools.chain(Knight._moves(*self.pos), Queen._moves(*self.pos)):
            for pos in streak:
                if not self.game.in_bounds(pos):
                    break
                if pos in self.board:
                    if self.pos in self.board[pos].base_moves():
                        yield pos
                    break
    def _moves(self, x, y):
        for a in range(x-1, x+2):
            for b in range(y-1, y+2):
                if (a, b) != (x, y):
                    yield [(a, b)]

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
        yield from self.base_moves()
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

first_row = [Rook, Knight, Bishop, Queen, King, Bishop, Knight, Rook]

S = 45

pieces_image = Image(source='chess.png').texture

for x, piece in enumerate([King, Queen, Rook, Bishop, Knight, Pawn]):
    piece._images = [pieces_image.get_region(S*x, S*y, S, S) for y in range(6)][::-1]

for preference, piece in enumerate([King, Pawn, Knight, Bishop, Rook, Queen]):
    piece.move_preference = preference
