from peer_constant import BUF_SIZE, CHUNK_DATA_SIZE, HEADER_LEN, MAX_PAYLOAD, MY_TEAM
from congestion_controller import *
from sending_window import *


class PeerState:
    def __str__(self) -> str:
        return self.__dict__.__str__()
    def __init__(self) -> None:
        self.receiving_connections = []
        self.sending_connections = []
        self.connections:List[TcpLikeConnection] = []
        self.cur_connection = None
        self.ack = 0

        # todo
        # self.peer_num

    def findConnection(self, addr):
        for con in self.connections:
            if addr == con.connect_peer:
                return con
        return None

    def addConnection(self, addr):
        newConnection = TcpLikeConnection(connect_peer=addr)
        self.connections.append(newConnection)
        return newConnection

    def removeConnection(self, addr):
        for i in range(len(self.connections)):
            if addr == self.connections[i].connect_peer:
                self.connections.pop(i)
                return True
        return False


# class DownloadMission:
#     def __init__(self, eof, erc, edc):
#         self.ex_output_file = eof
#         self.ex_received_chunk = erc
#         self.ex_downloading_chunkhash = edc


class TcpLikeConnection:
    def __str__(self) -> str:
        return self.__dict__.__str__()
    def __init__(self, sending_peer=0, receiving_peer=1, sending_seqnum=0, receiving_seq_num=0,
                 connect_peer=()) -> None:
        """TCP 连接状态
        Args:
            sending_peer (int, optional): _description_. Defaults to 0.
            receiving_peer (int, optional): _description_. Defaults to 1.
            sending_seqnum (int, optional): 发送方将要发的下一个. Defaults to 0.
            receiving_seq_num (int, optional): _description_. Defaults to 0.
        """
        self.sending_peer = sending_peer
        self.receiving_peer = receiving_peer
        self.connect_peer = connect_peer
        self.is_sender = True

        self.sending_seq_num = sending_seqnum
        self.receiving_seq_num = receiving_seq_num

        self.ex_sending_chunkhash = ""  # sending mission
        self.ex_downloading_chunkhash = ""
        self.has_chunk_list = []

        self.congestion_controller = CongestionController()
        self.sending_wnd = TcpSendingWindow()

        self.last_receive_time = 0

        self.cwnd_plot = []
        self.time_plot = []
