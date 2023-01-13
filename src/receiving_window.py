class TcpReceivingWindow:
    def __init__(self):
        self.ack = 1  # 第一个DATA包是1

    def try_receive(self, seq):
        if seq == self.ack:
            self.ack += 1
            return True
        else:
            return False
