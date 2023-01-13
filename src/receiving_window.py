class TcpReceivingWindow:
    def __init__(self):
        self.ack = 0  # 第一个DATA包是1

    def try_receive(self, seq):
        if seq == self.ack+1:
            self.ack += 1
            return True
        else:
            return False
