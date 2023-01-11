import time
from typing import List

# from queue import Queue

from src.peer_packet import PeerPacket
from util.simsocket import SimSocket


class TimedPacket:
    def __init__(self, peer_packet: PeerPacket, send_time=time.time()) -> None:
        self.peer_packet = peer_packet
        self.send_time = send_time


class SendingWindow:
    def __init__(self):
        # self.sent_pkt_list: Queue[TimedPacket] = Queue()
        self.sent_pkt_list: List[TimedPacket] = []
        self.front_seq = 0
        self.window_size = 1  # 以packet为单位
        self.timeout = 0.5

    def seq2index(self, seq):
        return seq - self.front_seq

    def try_acknowledge(self, ack):
        """
        ack is the seq number of the packet that is acknowledged. 单位是packet, 不是Byte
        """
        if ack <= self.front_seq:
            # Duplicated ACK 出现了
            return False
        for i in range(self.seq2index(ack)):
            self.sent_pkt_list.pop()
        self.front_seq = ack
        return True

    def timeout_packets(self):
        now = time.time()
        return list(
            filter(lambda timed_packet: now - timed_packet.send_time > self.timeout,
                   self.sent_pkt_list)
        )

    def put_packet(self, peer_packet: PeerPacket):
        if len(self.sent_pkt_list) < self.window_size:
            if len(self.sent_pkt_list) + 1 == self.window_size:
                pass  # 包装 TCP_Window_Full 字段到 peer_packet
            self.sent_pkt_list.append(TimedPacket(peer_packet))
            return True
        return False

    def fetch_data(self, ack):
        return self.sent_pkt_list[ack]
