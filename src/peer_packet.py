from enum import Enum
class PeerPacketType(Enum):
    WHOHAS = 0
    IHAVE = 1
    GET = 2
    DATA = 3
    ACK = 4
    DENIED = 5
    # def get_strategy(self):
    #     if self==PeerPacketType.WHOHAS:
    #         return whoHasStrategy

# def whoHasStrategy()


from peer_constant import *


class PeerPacket:
    def __init__(self, magic_num=52305, team_num=MY_TEAM, type_code=0, header_len=HEADER_LEN, pkt_len=HEADER_LEN, seq_num=0, ack_num=0, data=bytes()) -> None:
        self.magic_num = magic_num
        self.team_num = team_num
        self.type_code = type_code
        self.header_len = header_len
        self.pkt_len = pkt_len
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.data = data

    def make_binary(self):
        return struct.pack("!HBBHHII", self.magic_num, self.team_num,
                           self.type_code, self.header_len, self.pkt_len,
                           self.seq_num, self.ack_num)+self.data

    @staticmethod
    def build(binary):
        Magic, Team, Type, hlen, plen, Seq, Ack = struct.unpack(
            "!HBBHHII", binary[:HEADER_LEN])  # add !
        data = binary[HEADER_LEN:]
        return PeerPacket(Magic, Team, Type, hlen, plen, Seq, Ack, data)