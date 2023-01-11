import time
from typing import List

# from queue import Queue

from src.peer_packet import PeerPacket
from util.simsocket import SimSocket


class TimeoutEstimator:
    def __init__(self, alpha: float = 1.0 / 8, beta: float = 1.0 / 8, sigma: float = 4, init_rtt: float = 1,
                 update_interval: int = 1):
        """超时估计器。参考TCP的计算公式。
        Args:
            alpha (float, optional): 对新的SampleRTT的接受程度. Defaults to 1.0/8.
            beta (float, optional): 对新的DevRTT的接受程度. Defaults to 1.0/8.
            sigma (float, optional): 置信区间的一半大小. Defaults to 4.
            init_rtt (float, optional): 初始的超时时间. Defaults to 1.
            update_interval (int, optional): 更新的间隔. Defaults to 1.
        """
        self.alpha = alpha
        self.beta = beta
        self.sigma = sigma

        self.estimate_rtt = init_rtt
        self.dev_rtt = 0

        self.timeout_interval = init_rtt

        self.updates = 0
        self.update_interval = update_interval

    def check_whether_timeout(self, time_waited: float):
        # if self.updates / self.update_interval == 0: return False # 如果采样次数不够，就不超时
        result = time_waited > self.timeout_interval
        if result:
            self.timeout_interval *= 2  # 超时后，timeout_interval翻倍，以免过早出现超时。
        return result

    def update(self, sample_rtt: float):
        self.updates += 1
        if self.updates % self.update_interval != 0:
            return
        # 到了采样间隔，才更新。
        self.estimate_rtt += self.alpha * (sample_rtt - self.estimate_rtt)
        sample_dev_rtt = abs(sample_rtt - self.estimate_rtt)
        self.dev_rtt += self.beta * (sample_dev_rtt - self.dev_rtt)
        # 每次采样，重新计算 timeout_interval。 之前 <<=1可能让timeout_interval过大。
        self.timeout_interval = self.estimate_rtt + self.sigma * self.dev_rtt


class TimedPacket:
    def __init__(self, peer_packet: PeerPacket, send_time=time.time()) -> None:
        self.peer_packet = peer_packet
        self.send_time = send_time


class SendingWindow:
    def __init__(self, timeout_estimator: TimeoutEstimator, init_seq=0, init_win_size=1, ) -> None:
        self.sent_pkt_list: List[TimedPacket] = []
        self.front_seq = init_seq
        self.window_size = init_win_size  # 以packet为单位
        self.timeout = timeout_estimator

    def seq2index(self, seq):
        return seq - self.front_seq

    def index2seq(self, index):
        return index + self.front_seq

    def try_acknowledge(self, ack) -> bool:
        """当收到新的ACK报文时，尝试更新发送窗口的状态。
        如果收到的ACK报文是重复的（表明接受方没有收到窗口中的packet），返回False，否则返回True。
        Args:
            ack (int): 单位是packet, 不是Byte。
        Returns:
            bool: 是否是 Duplicated ACK。 如果是，外面还要根据情况看看要不要快速重传。
        """
        if ack <= self.front_seq:
            # Duplicated ACK 出现了
            return False
        for i in range(self.seq2index(ack)):
            pkt = self.sent_pkt_list.pop()
            self.timeout.update(time.time() - pkt.send_time)  # 更新 rtt 的估计。
        self.front_seq = ack
        return True

    def timeout_packets_seq(self) -> List[int]:
        """周期性调用本函数，检查 Sending Window 中的包是否超时。
        Returns:
            List[int]: 超时的包的序号列表。
        """
        now = time.time()
        return list(map(self.index2seq,
                        filter(lambda idx: self.timeout.check_whether_timeout(now - self.sent_pkt_list[idx].send_time),
                               range(len(self.sent_pkt_list)))))

    def put_packet(self, peer_packet: PeerPacket) -> bool:
        """尝试放入一个新的包。
            如果发送窗口已满，方法返回False，发送方应该暂停发送。
            否则，将包放入发送窗口并设定发送时间为现在，返回True。
        Args:
            peer_packet (PeerPacket): _description_

        Returns:
            bool: 根据网络情况，是否应该发送包。
        """
        if len(self.sent_pkt_list) < self.window_size:
            if len(self.sent_pkt_list) + 1 == self.window_size:
                pass  # 包装 TCP_Window_Full 字段到 peer_packet
            self.sent_pkt_list.append(TimedPacket(peer_packet))
            return True
        return False

    def fetch_data(self, seq: int) -> TimedPacket:
        """获取发送窗口中的数据。
        
        Args:
            seq (int): 要获取的packet的序号。
        Returns:
            TimedPacket: 含有发送时间的packet的引用。
        """
        return self.sent_pkt_list[self.seq2index(seq)]
