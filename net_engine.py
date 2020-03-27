import marshal
import random
import select
import socket
import threading
import time
import urllib.error
import urllib.request

import stun

import env

def poll(sock):
    return select.select([sock], [], [], 0)[0] != []

def any_actions(actions):
    return any(acts for _, acts in actions)

class NetEngine:
    latency = 5
    replay_max_wait = 30

    def __init__(self, game_model):
        self.game = game_model
        self.socket = None
        self.threads = []
        self.reset()
        self.instance_id = random.randrange(2**64)

    def reset(self):
        self.peers = []
        self.address = None
        self.last_comm_time = None
        self.comm_gap_msg_at = 10
        self.should_start_replay = False
        self.iter_actions = {}

    def start(self):
        self.game.player = 0
        self.game.reset()
        self.should_stop = False
        net_thread = threading.Thread(target=self.net_thread_go)
        self.threads.append(net_thread)
        if not env.dev_mode:
            net_thread.start()

    def net_thread_go(self):
        self.setup_socket()
        if self.should_stop:
            return
        self.setup_addr_name()
        if self.should_stop:
            return
        self.wait_for_connections()

    def setup_socket(self):
        while True:
            local_port = random.randint(1024, 65535)
            try:
                if self.should_stop:
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
        self.game.add_message('')
        self.game.add_message('Your address is:')
        self.game.add_message(self.address.upper())
        self.game.add_message('')
        self.game.add_message('Type the address of a friend to play with them')

    def wait_for_connections(self):
        while not self.peers:
            time.sleep(5)
            if self.should_stop:
                return
            url = 'http://game-match.herokuapp.com/lookup/chess2/%s/' % self.address.replace(' ', '%20')
            print('checking game at %s' % url)
            self.add_peers(urllib.request.urlopen(url).read().decode('utf-8'))

    def connect(self, address):
        connect_thread = threading.Thread(target=self.connect_thread_go, args=(address, ))
        self.threads.append(connect_thread)
        connect_thread.start()

    def connect_thread_go(self, addr):
        self.game.add_message('Establishing connection with: %s' % addr)
        while self.address is None:
            # Net thread didn't finish
            time.sleep(1)
        url = 'http://game-match.herokuapp.com/connect/chess2/%s/%s/' % (self.address.replace(' ', '%20'), addr.lower().replace(' ', '%20'))
        print('looking up host at %s' % url)
        try:
            response = urllib.request.urlopen(url).read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                self.game.add_message('No such game: %s' % addr)
            else:
                self.game.add_message('Server error when looking up game: %s' % addr)
            return
        self.add_peers(response.decode('utf-8'))
        self.game.player = 1

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
            self.game.messages.clear()
            self.game.add_message('')
            self.game.add_message('Connection successful!')
            self.game.add_message('THE GAME BEGINS!')
            self.game.mode = 'play'
            self.last_comm_time = time.time()
            self.comm_gap_msg_at = 10

    def communicate(self):
        if self.socket is None:
            return
        packet = marshal.dumps((
            self.instance_id,
            [(i, self.iter_actions.setdefault(i, {}).setdefault(self.instance_id, []))
                for i in
                range(
                    max(0, self.game.counter-self.latency),
                    self.game.counter+self.latency)]))
        for peer in self.peers:
            self.socket.sendto(packet, 0, peer)
        while poll(self.socket):
            self.last_comm_time = time.time()
            packet, peer = self.socket.recvfrom(0x1000)
            peer_id, peer_iter_actions = marshal.loads(packet)
            for i, actions in peer_iter_actions:
                acts = self.iter_actions.setdefault(i, {})
                if peer_id in acts:
                    assert acts[peer_id] == actions, '%s %s' % (acts[peer_id], actions)
                else:
                    acts[peer_id] = actions

        if self.last_comm_time is None:
            return
        time_since_comm = time.time() - self.last_comm_time
        if time_since_comm >= self.comm_gap_msg_at:
            self.game.add_message('No communication for %d seconds' % self.comm_gap_msg_at)
            self.comm_gap_msg_at += 5
        elif time_since_comm < 5:
            self.comm_gap_msg_at = 5

    def get_replay_actions(self):
        return sorted(self.iter_actions.get(self.game.counter, {}).items())

    def act(self):
        if self.game.mode == 'replay':
            all_actions = self.get_replay_actions()
            if any_actions(all_actions):
                self.replay_wait = 0
            else:
                self.game.counter += 1
                all_actions = self.get_replay_actions()
                self.replay_wait += 1
                if self.replay_wait == self.replay_max_wait:
                    self.replay_wait = 0
                    while not any_actions(all_actions) and self.game.counter+1 < self.replay_stop:
                        self.game.counter += 1
                        all_actions = self.get_replay_actions()
        elif self.game.active():
            if self.game.counter < self.latency:
                self.game.counter += 1
                return
            if len(self.iter_actions.get(self.game.counter, {})) <= len(self.peers):
                # We haven't got communications from all peers for this iteration.
                # So we'll wait.
                return
            all_actions = sorted(self.iter_actions[self.game.counter].items())
        else:
            return

        for i, actions in all_actions:
            nick = 'You' if i == self.instance_id else 'Friend'
            for action_type, params in actions:
                action_func = getattr(self.game, 'action_'+action_type, None)
                if action_func is None:
                    self.game.add_message(action_type + ': no such action')
                else:
                    prev_messages = len(self.game.messages)
                    if env.dev_mode:
                        action_func(nick, *params)
                    else:
                        try:
                            action_func(nick, *params)
                        except:
                            self.game.add_message('action ' + action_type + ' failed')
                    if prev_messages == len(self.game.messages):
                        self.game.add_message(action_type.upper())

        self.game.counter += 1

        if self.game.mode == 'replay' and self.game.counter == self.replay_stop:
            self.game.mode = 'play'
            self.game.last_start = self.game.counter
            self.game.init()
        assert not self.game.mode == 'replay' or self.game.counter < self.replay_stop

        if self.should_start_replay:
            self.should_start_replay = False
            print('start replay!')
            self.game.mode = 'replay'
            self.replay_stop = self.game.counter
            self.game.counter = self.game.last_start
            self.replay_wait = 0
            self.game.init()

    def iteration(self):
        self.communicate()

        if self.game.mode != 'replay' and self.instance_id not in self.iter_actions.setdefault(self.game.counter+self.latency, {}):
            self.iter_actions[self.game.counter+self.latency][self.instance_id] = self.game.cur_actions
            self.game.cur_actions = []

        self.act()

    def start_replay(self):
        self.should_start_replay = True
