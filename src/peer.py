import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from enum import Enum
from peer_state import *
from peer_packet import *
from peer_constant import BUF_SIZE, CHUNK_DATA_SIZE, HEADER_LEN, MAX_PAYLOAD, MY_TEAM

import pickle
import argparse
import hashlib
import util.bt_utils as bt_utils
import socket
import struct
import util.simsocket as simsocket
import select

"""
This is CS305 project skeleton code.
Please refer to the example files - example/dumpreceiver.py and example/dumpsender.py - to learn how to play with this skeleton.
"""

config = None

# 为了实现并发，移动到了 TCPLikeConnection 中
# ex_downloading_chunkhash = ""
ex_output_file = None
ex_received_chunk = dict()
needed_chunk_ist = []

this_peer_state = PeerState()

EstimateRTT = 0
DevRTT = 0
TimeoutIntervel = 0

dupACKCnt = 0
cwnd = 1
sshresh = 64


def re_slow_start(ex_cwnd):
    global dupACKCnt, cwnd, sshresh

    cwnd = 1
    sshresh = max(ex_cwnd / 2, 2)
    dupACKCnt = 0


class TimeoutEstimator:
    def __init__(self, alpha=1.0 / 8, beta=1.0 / 8, sigma=4):
        self.alpha = alpha
        self.beta = beta
        self.sigma = sigma

        self.estimate_rtt = 0
        self.dev_rtt = 0

    def check_whether_timeout(self, time_waited):
        return time_waited > self.estimate_rtt + self.sigma * self.dev_rtt

    def update(self, sample_rtt):
        self.estimate_rtt += self.alpha * (sample_rtt - self.estimate_rtt)
        self.dev_rtt += self.beta * (abs(sample_rtt - self.estimate_rtt) - self.dev_rtt)


def process_inbound_udp(sock):
    global config
    # global ex_sending_chunkhash

    # Receive pkt
    pkt, from_addr = sock.recvfrom(BUF_SIZE)
    peer_packet = PeerPacket.build(pkt)

    # judge the peer connection
    this_peer_state.cur_connection = this_peer_state.findConnection(from_addr)
    if this_peer_state.cur_connection is None:
        this_peer_state.cur_connection = this_peer_state.addConnection(from_addr)

    print(
        f"prepared to send to {this_peer_state.cur_connection.connect_peer} with [team:{peer_packet.Team}, type:{peer_packet.Type}, "
        f"Seq:{peer_packet.Seq}, Ack:{peer_packet.Ack}")

    ex_sending_chunkhash = this_peer_state.cur_connection.ex_sending_chunkhash

    packet_type = PeerPacketType(peer_packet.Type)

    # ----------------------------- sender part -------------------------------------
    if packet_type == PeerPacketType.WHOHAS:
        LOGGER.debug("接收到WHOHAS询问。")
        # received an WHOHAS pkt
        # see what chunk the sender has
        whohas_chunk_hash = peer_packet.data[:20]
        # bytes to hex_str
        chunkhash_str = bytes.hex(whohas_chunk_hash)
        this_peer_state.cur_connection.ex_sending_chunkhash = chunkhash_str

        print(f"whohas: {chunkhash_str}, has: {list(config.haschunks.keys())}")
        if chunkhash_str in config.haschunks:
            # send back IHAVE pkt
            ihave_header = struct.pack(
                "!HBBHHII", 52305, MY_TEAM, PeerPacketType.IHAVE.value, HEADER_LEN, HEADER_LEN + len(whohas_chunk_hash),
                0, 0)
            ihave_pkt = ihave_header + whohas_chunk_hash
            sock.sendto(ihave_pkt, from_addr)

    elif packet_type == PeerPacketType.GET:
        # received a GET pkt
        # 判断是否超过最大发送次数
        if len(this_peer_state.sending_connections) >= config.max_conn:
            LOGGER.warning("连接数量超过最大限制，发送拒绝报文。")
            # sock.send
            # denied seq和ack都是0就行。
            deny_packet = PeerPacket(type_code=PeerPacketType.DENIED.value)
            sock.sendto(deny_packet.make_binary(), from_addr)
            this_peer_state.removeConnection(from_addr)
            return  # added

        # 感觉要改，识别 GET 里真正申请的部分
        chunk_data = config.haschunks[ex_sending_chunkhash][:MAX_PAYLOAD]

        # send back DATA
        data_header = struct.pack(
            "!HBBHHII", 52305, MY_TEAM, 3, HEADER_LEN, HEADER_LEN, 1, 0)
        sock.sendto(data_header + chunk_data, from_addr)

    elif packet_type == PeerPacketType.ACK:
        # received an ACK pkt

        ack_num = peer_packet.Ack

        if ack_num * MAX_PAYLOAD >= CHUNK_DATA_SIZE:
            # finished
            print(f"finished sending {ex_sending_chunkhash} to {from_addr}")
            pass
        else:
            left = ack_num * MAX_PAYLOAD
            right = min((ack_num + 1) * MAX_PAYLOAD, CHUNK_DATA_SIZE)
            next_data = config.haschunks[ex_sending_chunkhash][left: right]

            # send next data
            data_header = struct.pack(
                "!HBBHHII", 52305, MY_TEAM, 3, HEADER_LEN, HEADER_LEN + len(next_data), ack_num + 1, 0)
            sock.sendto(data_header + next_data, from_addr)

    # ------------------------------- receiver part --------------------------------
    elif packet_type == PeerPacketType.IHAVE:
        # received an IHAVE pkt
        # see what chunk the sender has
        get_chunk_hash = peer_packet.data[:20]

        # send back GET pkt
        get_header = struct.pack(
            "!HBBHHII", 52305, MY_TEAM, PeerPacketType.GET.value, HEADER_LEN, HEADER_LEN + len(get_chunk_hash), 0, 0)
        get_pkt = get_header + get_chunk_hash
        sock.sendto(get_pkt, from_addr)

        # update connection info

    # elif type == PeerPacketType.DATA:
    #     # received a DATA pkt
    #     ex_received_chunk[ex_downloading_chunkhash] += data
    #
    #     # send back ACK
    #     ack_pkt = struct.pack("!HBBHHII", 52305, MY_TEAM, 4,
    #                           HEADER_LEN, HEADER_LEN, 0, Seq)
    #     sock.sendto(ack_pkt, from_addr)
    #
    #     # see if finished
    #     if len(ex_received_chunk[ex_downloading_chunkhash]) == CHUNK_DATA_SIZE:
    #         # finished downloading this chunkdata!
    #         # dump your received chunk to file in dict form using pickle
    #         with open(ex_output_file, "wb") as wf:
    #             pickle.dump(ex_received_chunk, wf)
    #
    #         # add to this peer's haschunk:
    #         config.haschunks[ex_downloading_chunkhash] = ex_received_chunk[ex_downloading_chunkhash]
    #
    #         # you need to print "GOT" when finished downloading all chunks in a DOWNLOAD file
    #         print(f"GOT {ex_output_file}")
    #
    #         # The following things are just for illustration, you do not need to print out in your design.
    #         sha1 = hashlib.sha1()
    #         sha1.update(ex_received_chunk[ex_downloading_chunkhash])
    #         received_chunkhash_str = sha1.hexdigest()
    #         print(f"Expected chunkhash: {ex_downloading_chunkhash}")
    #         print(f"Received chunkhash: {received_chunkhash_str}")
    #         success = ex_downloading_chunkhash == received_chunkhash_str
    #         print(f"Successful received: {success}")
    #         if success:
    #             print("Congrats! You have completed the example!")
    #         else:
    #             print("Example fails. Please check the example files carefully.")


def process_download(sock, chunkfile, outputfile):
    '''
    receiver part
    if DOWNLOAD is used, the peer will keep getting files until it is done
    '''
    # print('PROCESS GET SKELETON CODE CALLED.  Fill me in! I\'ve been doing! (', chunkfile, ',     ', outputfile, ')')
    global ex_output_file
    global ex_received_chunk
    # global ex_downloading_chunkhash
    global needed_chunk_ist

    # this_peer_state.cur_connection.ex_output_file = outputfile
    ex_output_file = outputfile

    # Step 1: read chunkhash to be downloaded from chunkfile
    download_hash = bytes()
    with open(chunkfile, 'r') as cf:
        for line in cf.readlines():
            index, datahash_str = line.strip().split(" ")
            ex_received_chunk[datahash_str] = bytes()
            needed_chunk_ist.append(datahash_str)
            # ex_downloading_chunkhash = datahash_str

            # hex_str to bytes
            datahash = bytes.fromhex(datahash_str)
            download_hash = download_hash + datahash

    # Step2: make WHOHAS pkt
    # |2byte magic|1byte type |1byte team|
    # |2byte  header len  |2byte pkt len |
    # |      4byte  seq                  |
    # |      4byte  ack                  |
    whohas_header = struct.pack(
        "!HBBHHII", 52305, MY_TEAM, PeerPacketType.WHOHAS.value, HEADER_LEN, HEADER_LEN + len(download_hash), 0, 0)
    whohas_pkt = whohas_header + download_hash
    info = struct.unpack("!HBBHHII", whohas_header)

    # Step3: flooding whohas to all peers in peer list
    peer_list = config.peers
    for p in peer_list:
        if int(p[0]) != config.identity:
            sock.sendto(whohas_pkt, (p[1], int(p[2])))
            print(f"send whohas to ({p[1]}:{p[2]}) with {info}")


def process_user_input(sock):
    command, chunkf, outf = input().split(' ')
    if command == 'DOWNLOAD':
        process_download(sock, chunkf, outf)
    else:
        pass


def peer_run(config):
    addr = (config.ip, config.port)
    sock = simsocket.SimSocket(config.identity, addr, verbose=config.verbose)

    try:
        while True:
            ready = select.select([sock, sys.stdin], [], [], 0.1)
            read_ready = ready[0]
            if len(read_ready) > 0:
                if sock in read_ready:
                    process_inbound_udp(sock)
                if sys.stdin in read_ready:
                    process_user_input(sock)
            else:
                # No pkt nor input arrives during this period
                pass
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


from datetime import datetime

_current_time = f"_{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
import logging

LOGGER: logging.Logger = None


def start_logger(verbose_level, id):
    global LOGGER
    LOGGER = logging.getLogger(f"SRC PEER{id}_LOGGER")
    LOGGER.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s -+- %(name)s -+- %(levelname)s -+- %(message)s")
    if verbose_level > 0:
        if verbose_level == 1:
            sh_level = logging.WARNING
        elif verbose_level == 2:
            sh_level = logging.INFO
        elif verbose_level == 3:
            sh_level = logging.DEBUG
        else:
            sh_level = logging.INFO
        sh = logging.StreamHandler(stream=sys.stdout)
        sh.setLevel(level=sh_level)
        sh.setFormatter(formatter)
        LOGGER.addHandler(sh)
    # 我们自己写的代码的 logger, 存放在src-log而不是log目录下，方便查看
    log_dir = "src-log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    fh = logging.FileHandler(filename=os.path.join(log_dir, f"src-peer{id}{_current_time}.log"), mode="w")

    fh.setLevel(level=logging.DEBUG)
    fh.setFormatter(formatter)
    LOGGER.addHandler(fh)
    LOGGER.info("Start logging")


if __name__ == '__main__':
    """
    -p: Peer list file, it will be in the form "*.map" like nodes.map.
    -c: Chunkfile, a dictionary dumped by pickle. It will be loaded automatically in bt_utils. The loaded dictionary has the form: {chunkhash: chunkdata}
    -m: The max number of peer that you can send chunk to concurrently. If more peers ask you for chunks, you should reply "DENIED"
    -i: ID, it is the index in nodes.map
    -v: verbose level for printing logs to stdout, 0 for no verbose, 1 for WARNING level, 2 for INFO, 3 for DEBUG.
    -t: pre-defined timeout. If it is not set, you should estimate timeout via RTT. If it is set, you should not change this time out.
        The timeout will be set when running test scripts. PLEASE do not change timeout if it set.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-p', type=str, help='<peerfile>     The list of all peers', default='example/ex_nodes_map')
    parser.add_argument(
        '-c', type=str, help='<chunkfile>    Pickle dumped dictionary {chunkhash: chunkdata}',
        default="example/data2.fragment")
    parser.add_argument(
        '-m', type=int, help='<maxconn>      Max # of concurrent sending',
        default=1)
    parser.add_argument(
        '-i', type=int, help='<identity>     Which peer # am I?',
        default=1)
    parser.add_argument('-v', type=int, help='verbose level', default=3)
    parser.add_argument('-t', type=int, help="pre-defined timeout", default=0)
    args = parser.parse_args()
    start_logger(args.v, args.i)

    config = bt_utils.BtConfig(args)
    peer_run(config)
