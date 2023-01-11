class PeerState:
    def __init__(self) -> None:    
        self.receiving_connections = []
        self.sending_connections = []
        

class TcpLikeConnection:
    def __init__(self, sending_peer=0, receiving_peer=1, sending_seqnum=0, receiving_seq_num=0) -> None:
        """TCP 连接状态

        Args:
            sending_peer (int, optional): _description_. Defaults to 0.
            receiving_peer (int, optional): _description_. Defaults to 1.
            sending_seqnum (int, optional): 发送方将要发的下一个. Defaults to 0.
            receiving_seq_num (int, optional): _description_. Defaults to 0.
        """
        self.sending_peer = sending_peer
        self.receiving_peer = receiving_peer
        self.sending_seq_num = sending_seqnum  
        self.receiving_seq_num = receiving_seq_num
        self.ACK_counter = 0

    def ACK_counter():
        
        if self.ACK_counter >= 4:
            return retransmit_enable


