

class Window():
    def __init__(self):
        self.pkt_list = []

    def size(self):
        return len(self.pkt_list)

    def add_pkt(self, pkt):
        self.pkt_list.append(pkt)

    def remove_pkt_front(self, pkt_inx):
        del self.pkt_list[:pkt_inx]
        