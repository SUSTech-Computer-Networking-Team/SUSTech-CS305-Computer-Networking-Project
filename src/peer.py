import os
import sys
import time

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
import matplotlib.pyplot as plt

"""
This is CS305 project skeleton code.
Please refer to the example files - example/dumpreceiver.py and example/dumpsender.py - to learn how to play with this skeleton.
"""

config = None

# 为了实现并发，移动到了 TCPLikeConnection 中
# ex_downloading_chunkhash = ""
ex_output_file = None
ex_received_chunk = dict()
needed_chunk_list = []

this_peer_state = PeerState()

cwnd_plot = []
time_plot = []
counter = 0


def check_timeout(sock: SimSocket) -> None:
    for conn in this_peer_state.connections:
        if not conn.is_sender: return
        sending_wnd: TcpSendingWindow = conn.sending_wnd
        timeout_packets = sending_wnd.timeout_packets_seq()
        if len(timeout_packets) == 0:
            continue
        congestion_controller = conn.congestion_controller
        for seq in timeout_packets:
            pkt = sending_wnd.fetch_data(seq)
            # 更新包时间
            pkt.send_time = time.time()
            # 重传.
            sock.sendto(pkt.peer_packet.make_binary(), conn.receiving_peer)
            # 更新congestion window
            congestion_controller.notify_timeout()


def process_inbound_udp(sock: SimSocket):
    global config
    global needed_chunk_list, ex_output_file, ex_received_chunk

    # global ex_sending_chunkhash
    # LOGGER.debug("进入process_inbound_udp函数")
    # Receive pkt
    pkt, from_addr = sock.recvfrom(BUF_SIZE)
    peer_packet = PeerPacket.build(pkt)
    # LOGGER.debug(f"从{from_addr}收到{peer_packet}")
    data = peer_packet.data

    # judge the peer connection
    this_peer_state.cur_connection = this_peer_state.findConnection(from_addr)
    if this_peer_state.cur_connection is None:
        this_peer_state.cur_connection = this_peer_state.addConnection(from_addr)
    # LOGGER.debug(f"恢复与{from_addr}的连接{this_peer_state.cur_connection}")

    print(
        f"prepared to response to {this_peer_state.cur_connection.connect_peer} with [team:{peer_packet.team_num}, "
        f"type:{peer_packet.type_code}, Seq:{peer_packet.seq_num}, Ack:{peer_packet.ack_num}]")

    packet_type = PeerPacketType(peer_packet.type_code)

    # ----------------------------- sender part -------------------------------------
    if packet_type == PeerPacketType.WHOHAS:
        LOGGER.debug("接收到 WHOHAS 询问。")
        # see what chunk the sender has
        # whohas_chunk_hash = data[:20]
        # bytes to hex_str

        # 如果已经和对方有连接，跳过，不能又发又接
        if this_peer_state.cur_connection.ex_sending_chunkhash != "" or\
                this_peer_state.cur_connection.ex_downloading_chunkhash != "":
            return

        chunkhash_list = bytes.hex(data)
        LOGGER.debug(f"whohas: {chunkhash_list}, has: {config.haschunks.keys()}")

        have_list = bytes()
        isHave = False

        l = 0
        r = 40
        while r <= len(chunkhash_list):
            if chunkhash_list[l:r] in config.haschunks.keys():
                have_list += bytes.fromhex(chunkhash_list[l:r])
                isHave = True
            l += 40
            r += 40

        if isHave:
            print(f"whohas: {chunkhash_list}, has: {bytes.hex(have_list)}")
            # send back IHAVE pkt
            ihave_header = struct.pack(
                "!HBBHHII", 52305, MY_TEAM, PeerPacketType.IHAVE.value, HEADER_LEN, HEADER_LEN + len(have_list), 0, 0)
            ihave_pkt = ihave_header + have_list
            sock.sendto(ihave_pkt, from_addr)
        else:
            this_peer_state.removeConnection(from_addr)

        # this_peer_state.cur_connection.ex_sending_chunkhash = chunkhash_str

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

        # 识别 GET 里真正申请的部分
        get_hash = bytes.hex(data)
        print(f"want to GET {get_hash}")
        chunk_data = config.haschunks[get_hash][:MAX_PAYLOAD]


        # send back DATA

        # data_header = struct.pack(
        #     "!HBBHHII", 52305, MY_TEAM, 3, HEADER_LEN, HEADER_LEN, 1, 0)
        # sock.sendto(data_header + chunk_data, from_addr)

        sending_wnd = this_peer_state.cur_connection.sending_wnd
        send_packet = PeerPacket(type_code=PeerPacketType.DATA.value, seq_num=1
                                 , data=chunk_data)

        if sending_wnd.put_packet(send_packet):
            # 没有超过窗口大小
            sock.sendto(send_packet.make_binary(), from_addr)
            this_peer_state.cur_connection.ex_sending_chunkhash = get_hash
            this_peer_state.sending_connections.append(this_peer_state.cur_connection)
            this_peer_state.cur_connection.receiving_peer = from_addr
            this_peer_state.cur_connection.sending_peer = (config.ip, config.port)

        else:
            # this_peer_state.removeConnection(from_addr)
            LOGGER.error("WARN!!!!!!!!!!!!")


    elif packet_type == PeerPacketType.ACK:
        # received an ACK pkt
        ex_sending_chunkhash = this_peer_state.cur_connection.ex_sending_chunkhash

        congestion_controller = this_peer_state.cur_connection.congestion_controller
        sending_wnd = this_peer_state.cur_connection.sending_wnd
        cwnd_plot = this_peer_state.cur_connection.cwnd_plot
        time_plot = this_peer_state.cur_connection.time_plot
        # time_plot_cnt = this_peer_state.cur_connection.time_plot_cnt

        ack_num = peer_packet.ack_num

        # 判断是否是dupACK
        if sending_wnd.try_acknowledge(ack_num + 1):
            # 不是dupACK
            congestion_controller.notify_new_ack()
            sending_wnd.window_size = congestion_controller.cwnd()

            cwnd_plot.append(congestion_controller.cwnd())
            time_plot.append(time.time())

            if ack_num * MAX_PAYLOAD >= CHUNK_DATA_SIZE:
                # 先判断是否完成整个chunk的传输
                # finished
                print(f"finished sending {ex_sending_chunkhash} to {from_addr}")

                # 画出cc的图
                plt.plot(time_plot,cwnd_plot,color='green', marker='o', linestyle='dashed', linewidth=1, markersize=3)
                plt.savefig(f"{from_addr}.png")
                plt.show()

                this_peer_state.removeConnection(from_addr)
            else:
                left = ack_num * MAX_PAYLOAD
                right = min((ack_num + 1) * MAX_PAYLOAD, CHUNK_DATA_SIZE)
                next_data = config.haschunks[ex_sending_chunkhash][left: right]

                send_packet = PeerPacket(type_code=PeerPacketType.DATA.value, seq_num=ack_num + 1
                                         , data=next_data)
                if sending_wnd.put_packet(send_packet):
                    # 没有超过窗口大小
                    sock.sendto(send_packet.make_binary(), from_addr)

        else:
            # 是dupACK，应该更新congestion controller的状态
            # 根据当前的controller状态，判断dupACK counter是否满足重传条件
            congestion_controller.notify_duplicate()
            sending_wnd.window_size = congestion_controller.cwnd()

            cwnd_plot.append(congestion_controller.cwnd())
            time_plot.append(time.time())

            if congestion_controller.duplicate_ack_count >= 3:
                # 满足重传条件
                fast_retransmit_packet: TimedPacket = sending_wnd.fetch_data(ack_num)
                fast_retransmit_packet.send_time = time.time()  # 重传之后重新计时。
                sock.sendto(fast_retransmit_packet.peer_packet.make_binary(), from_addr)
            else:
                # 不满足重传条件
                pass


    # ------------------------------- receiver part --------------------------------
    elif packet_type == PeerPacketType.IHAVE:
        # received an IHAVE pkt
        # see what chunk the sender has
        get_chunk_list = bytes.hex(data)
        get_chunk_hash = bytes()

        l = 0
        r = 40
        while r <= len(get_chunk_list):
            chunk_hash = get_chunk_list[l:r]
            this_peer_state.cur_connection.has_chunk_list.append(chunk_hash)
            if chunk_hash in needed_chunk_list:
                get_chunk_hash = bytes.fromhex(chunk_hash)
                this_peer_state.cur_connection.ex_downloading_chunkhash = chunk_hash
                needed_chunk_list.remove(chunk_hash)
                break
            l += 40
            r += 40

        print(f"prepare to GET {bytes.hex(get_chunk_hash)}, still need {needed_chunk_list}")

        # send back GET pkt, if we need it.
        if len(get_chunk_hash) != 0:
            get_header = struct.pack(
                "!HBBHHII", 52305, MY_TEAM, PeerPacketType.GET.value, HEADER_LEN, HEADER_LEN + len(get_chunk_hash), 0,
                0)
            get_pkt = get_header + get_chunk_hash
            sock.sendto(get_pkt, from_addr)

            this_peer_state.cur_connection.is_sender = False
            this_peer_state.cur_connection.sending_peer = from_addr
            this_peer_state.cur_connection.receiving_peer = (config.ip, config.port)

            # update connection info
            this_peer_state.cur_connection.last_receive_time = time.time()


    elif packet_type == PeerPacketType.DATA:
        # received a DATA pkt
        ex_downloading_chunkhash = this_peer_state.cur_connection.ex_downloading_chunkhash
        ex_received_chunk[ex_downloading_chunkhash] += data

        # send back ACK
        ack_pkt = struct.pack("!HBBHHII", 52305, MY_TEAM, 4,
                              HEADER_LEN, HEADER_LEN, 0, peer_packet.seq_num)
        sock.sendto(ack_pkt, from_addr)
        this_peer_state.cur_connection.last_receive_time = time.time()

        # see if finished
        # todo 继续 send who has

        # finished downloading this chunkdata!
        if len(ex_received_chunk[ex_downloading_chunkhash]) == CHUNK_DATA_SIZE:

            # add to this peer's haschunk:
            config.haschunks[ex_downloading_chunkhash] = ex_received_chunk[ex_downloading_chunkhash]
            this_peer_state.removeConnection(from_addr)

            if len(needed_chunk_list) != 0:
                send_whohas(sock)

            # you need to print "GOT" when finished downloading all chunks in a DOWNLOAD file
            if checkFinish():
                with open(ex_output_file, "wb") as wf:
                    # dump your received chunk to file in dict form using pickle
                    pickle.dump(ex_received_chunk, wf)
                print(f"GOT {ex_output_file}")

            # The following things are just for illustration, you do not need to print out in your design.
            sha1 = hashlib.sha1()
            sha1.update(ex_received_chunk[ex_downloading_chunkhash])
            received_chunkhash_str = sha1.hexdigest()
            print(f"Expected chunkhash: {ex_downloading_chunkhash}")
            print(f"Received chunkhash: {received_chunkhash_str}")
            success = ex_downloading_chunkhash == received_chunkhash_str
            print(f"Successful received: {success}")
            if success:
                print("Congrats! You have completed the example!")
            else:
                print("Example fails. Please check the example files carefully.")


def checkFinish():
    for chunk_hash in ex_received_chunk.keys():
        if len(ex_received_chunk[chunk_hash]) != CHUNK_DATA_SIZE:
            return False
    return True


def process_download(sock, chunkfile, outputfile):
    """
    receiver part
    if DOWNLOAD is used, the peer will keep getting files until it is done
    """
    # print('PROCESS GET SKELETON CODE CALLED.  Fill me in! I\'ve been doing! (', chunkfile, ',     ', outputfile, ')')
    global ex_output_file
    global ex_received_chunk
    # global ex_downloading_chunkhash
    global needed_chunk_list

    # this_peer_state.cur_connection.ex_output_file = outputfile
    ex_output_file = outputfile

    # Step 1: read chunkhash to be downloaded from chunkfile
    download_hash = bytes()
    with open(chunkfile, 'r') as cf:
        for line in cf.readlines():
            index, chunk_hash = line.strip().split(" ")
            ex_received_chunk[chunk_hash] = bytes()
            needed_chunk_list.append(chunk_hash)
            # ex_downloading_chunkhash = datahash_str

    send_whohas(sock)


def send_whohas(sock):
    global needed_chunk_list

    download_hash = bytes()
    for chunk_hash in needed_chunk_list:
        download_hash += bytes.fromhex(chunk_hash)

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

            # 超时检查
            check_timeout(sock)

            # crash check
            for con in this_peer_state.connections:
                if con.last_receive_time != 0 and time.time() - con.last_receive_time >= 10:

                    crash_download_hash = con.ex_downloading_chunkhash
                    needed_chunk_list.append(crash_download_hash)
                    ex_received_chunk[crash_download_hash] = bytes()
                    this_peer_state.removeConnection(con.connect_peer)
                    send_whohas(sock)

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
    fh = logging.FileHandler(filename=os.path.join(log_dir, f"src{_current_time}-peer{id}.log"), mode="w")

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
    
